#!/usr/bin/env python3
"""Plan, test and undo local Claude Desktop catalogue imports.

Transcripts remain shared and immutable. Live writes require explicit --live and
a fully closed Desktop. No credential, automation or live-process files are
copied. Plans and backups contain private conversation metadata.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid
from urllib.parse import urlsplit

# The desktop loads this helper from signed app resources; never write bytecode
# caches into that bundle while executing the packaged backend.
sys.dont_write_bytecode = True
from asset_audit import audit_assets, recover_preserved_outputs, safe_asset_hash, is_link, assert_no_links
import sync_platform

LIVE_APP_DATA = sync_platform.default_app_data(strict=False)
LIVE_ROOT = LIVE_APP_DATA / "claude-code-sessions"
LIVE_PROJECTS = Path.home() / ".claude/projects"
_INITIAL_APP_DATA = LIVE_APP_DATA
_PATHS_CONFIGURED = False
SESSION_RE = re.compile(r"local_([0-9a-fA-F-]{36})")
UUID_RE = re.compile(r"[0-9a-fA-F-]{36}")
_LIVE_WRITE_PATHS = None
PORTABLE_KEYS = {
    "sessionId", "cliSessionId", "priorCliSessionIds", "cwd", "originCwd",
    "createdAt", "lastActivityAt", "title", "titleSource", "titleTurn",
    "model", "effort", "isArchived", "isStarred", "completedTurns",
    "forkedFromSessionId", "forkedAtMessageUuid", "lastAssistantUuid",
    "gitAnchors", "gitAnchorsFolderRealpath", "gitAnchorsLookupOnly",
    "writtenBranches", "rewindEdges", "transcriptCuts", "transcriptModelStates",
    "latestUserFrameAt", "postTurnSummary", "postTurnSummaryFor",
    "publishedArtifacts",
}
ARTIFACT_PATH_RE = re.compile(
    r"/(?:code/(?:artifact|frame)|artifact)/(?:[A-Za-z0-9_-]*-)?"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|"
    r"[1-9A-HJ-NP-Za-km-z]{22})"
)
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def artifact_identity(url):
    """Match the artifact URLs accepted by the installed Desktop loader."""
    if not isinstance(url, str) or len(url) > 2048:
        return None
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in ("claude.ai", "claude.com")
                or parsed.port not in (None, 443)
                or parsed.username or parsed.password):
            return None
        match = ARTIFACT_PATH_RE.fullmatch(parsed.path)
        if not match:
            return None
        identifier = match.group(1)
        if len(identifier) == 36:
            return str(uuid.UUID(identifier))
        number = 0
        for char in identifier:
            number = number * 58 + BASE58_ALPHABET.index(char)
        return str(uuid.UUID(int=number)) if number < 2 ** 128 else None
    except (ValueError, TypeError):
        return None


def clean_artifact(value):
    if not isinstance(value, dict) or artifact_identity(value.get("url")) is None:
        return None
    result = {"url": value["url"]}
    title = value.get("title")
    if isinstance(title, str) and title:
        result["title"] = title[:120]
    path = value.get("sourcePath")
    if isinstance(path, str) and path and len(path) <= 4096 and "\0" not in path:
        result["sourcePath"] = path
    timestamp = value.get("updatedAt")
    if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool) and abs(timestamp) <= 8.64e15:
        result["updatedAt"] = timestamp
    return result


def clean_artifacts(record):
    values = record.get("publishedArtifacts", [])
    if not isinstance(values, list):
        return []
    return [item for value in values if (item := clean_artifact(value)) is not None]


def history_record(record):
    """Artifact discoveries can differ without conflicting conversation history."""
    return {k: v for k, v in portable_record(record).items() if k != "publishedArtifacts"}


def event_artifact(entry):
    if not isinstance(entry, dict) or entry.get("type") != "frame-link":
        return None
    value = {"url": entry.get("frameUrl"), "title": entry.get("title"),
             "sourcePath": entry.get("path")}
    timestamp = entry.get("timestamp")
    if isinstance(timestamp, str) and len(timestamp) <= 64:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                value["updatedAt"] = parsed.timestamp() * 1000
        except (ValueError, OverflowError):
            pass
    return clean_artifact(value)


def transcript_artifacts(path):
    found = []
    with path.open("rb") as stream:
        for line in stream:
            if not line.strip():
                continue
            entry = json.loads(line)
            artifact = event_artifact(entry)
            if artifact:
                found.append(artifact)
            metadata = entry.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("artifacts"), list):
                for item in metadata["artifacts"][-200:]:
                    if not isinstance(item, dict):
                        continue
                    artifact = event_artifact({"type": "frame-link", "frameUrl": item.get("url"),
                                              "title": item.get("title"), "timestamp": item.get("updated_at")})
                    if artifact:
                        found.append(artifact)
    return found


def reconcile_artifacts(copies, index, valid_cache, artifact_cache):
    """Union discoveries by artifact UUID, preserving ambiguous latest metadata."""
    groups = {}
    transcripts = set()
    for _, record in copies:
        candidates = clean_artifacts(record)
        for sid in [record["cliSessionId"], *record.get("priorCliSessionIds", [])]:
            paths = index.get(sid, [])
            if len(paths) != 1:
                continue
            path = paths[0]
            if path not in valid_cache:
                valid_cache[path] = valid_transcript(path)
            if not valid_cache[path]:
                continue
            transcripts.add(path)
            if path not in artifact_cache:
                artifact_cache[path] = transcript_artifacts(path)
            candidates.extend(artifact_cache[path])
        for candidate in candidates:
            groups.setdefault(artifact_identity(candidate["url"]), []).append(candidate)
    chosen, conflicts = [], set()
    for identifier, candidates in sorted(groups.items()):
        latest = max(item.get("updatedAt", 0) for item in candidates)
        newest = [item for item in candidates if item.get("updatedAt", 0) == latest]
        # Equivalent URLs may use a frame, a slug or an artifact page for one UUID.
        if any(len({item[key] for item in newest if item.get(key)}) > 1
               for key in ("title", "sourcePath")):
            conflicts.add(identifier)
            continue
        item = dict(sorted(newest, key=lambda a: (-len(a), a["url"]))[0])
        for key in ("title", "sourcePath"):
            if not item.get(key):
                ordered = sorted(candidates, key=lambda a: a.get("updatedAt", 0), reverse=True)
                value = next((a[key] for a in ordered if a.get(key)), None)
                if value:
                    item[key] = value
        chosen.append(item)
    chosen.sort(key=lambda a: (-a.get("updatedAt", 0), artifact_identity(a["url"])))
    return chosen[:50], conflicts, transcripts


def with_artifacts(record, shared, conflicts):
    result = dict(record)
    preserved = [a for a in clean_artifacts(record) if artifact_identity(a["url"]) in conflicts]
    artifacts = sorted([*shared, *preserved],
                       key=lambda a: (-a.get("updatedAt", 0), artifact_identity(a["url"])))[:50]
    if artifacts:
        result["publishedArtifacts"] = artifacts
    else:
        result.pop("publishedArtifacts", None)
    return result


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(data) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def file_hash(path: Path):
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def private_dir(path: Path):
    assert_no_links(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def assert_test_root(root: Path):
    resolved = root.resolve()
    if _LIVE_WRITE_PATHS is not None and resolved in _LIVE_WRITE_PATHS:
        return
    for live in (LIVE_ROOT.resolve(), LIVE_APP_DATA.resolve(), LIVE_PROJECTS.resolve(),
                 (Path.home() / ".claude").resolve()):
        if resolved == live or live in resolved.parents or resolved in live.parents:
            raise RuntimeError("Live data is read-only without an explicit live operation.")
    if is_link(root):
        raise ValueError("The root directory cannot be a symbolic link.")
    assert_no_links(root)


def assert_claude_closed():
    if sync_platform.IS_WINDOWS and not _PATHS_CONFIGURED and LIVE_APP_DATA == _INITIAL_APP_DATA:
        if sync_platform.default_app_data() != LIVE_APP_DATA:
            raise RuntimeError("The Claude data location changed. Run the command again or use --app-data.")
    sync_platform.assert_claude_closed()


def configure_live_paths(app_data: Path | None = None, projects: Path | None = None):
    """Set an explicit live catalogue scope without changing the plan schema."""
    global LIVE_APP_DATA, LIVE_ROOT, LIVE_PROJECTS, _PATHS_CONFIGURED
    selected_app_data = (Path(app_data).expanduser().absolute() if app_data is not None
                         else sync_platform.default_app_data())
    selected_projects = (Path(projects).expanduser().absolute() if projects is not None
                         else Path.home() / ".claude/projects")
    assert_no_links(selected_app_data)
    assert_no_links(selected_projects)
    LIVE_APP_DATA = selected_app_data
    LIVE_ROOT = LIVE_APP_DATA / "claude-code-sessions"
    LIVE_PROJECTS = selected_projects
    _PATHS_CONFIGURED = True


@contextmanager
def live_write_scope(root: Path, changes: list, live=False):
    global _LIVE_WRITE_PATHS
    if not live:
        assert_test_root(root)
        yield
        return
    if is_link(root) or root.resolve() != LIVE_ROOT.resolve():
        raise ValueError("--live only allows the selected Claude local catalogue.")
    assert_no_links(root)
    assert_claude_closed()
    approved = {root.resolve()}
    for change in changes:
        path = safe_path(root, change["relative_path"])
        if (len(Path(change["relative_path"]).parts) != 3
                or (path.name != "archived-sessions.idx"
                    and (path.suffix != ".json" or not SESSION_RE.fullmatch(path.stem)))):
            raise ValueError("File is outside the scope of local chats.")
        approved.add(path.resolve())
    previous = _LIVE_WRITE_PATHS
    _LIVE_WRITE_PATHS = approved
    try:
        yield
    finally:
        _LIVE_WRITE_PATHS = previous


def safe_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("Invalid path in the plan.")
    target = root / rel
    if root.resolve() not in target.resolve().parents:
        raise ValueError("Path is outside the root directory.")
    for parent in [target, *target.parents]:
        if parent == root.parent:
            break
        if is_link(parent):
            raise ValueError("Symbolic links are not allowed in the catalogue.")
    return target


def atomic_write(path: Path, data: bytes):
    assert_test_root(path)
    private_dir(path.parent)
    fd, name = tempfile.mkstemp(prefix=".sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def portable_record(record: dict) -> dict:
    """Import history with fresh account-specific tools and permission grants."""
    clean = {k: v for k, v in record.items() if k in PORTABLE_KEYS}
    if "publishedArtifacts" in clean:
        artifacts = clean_artifacts(record)
        if artifacts:
            clean["publishedArtifacts"] = artifacts
        else:
            clean.pop("publishedArtifacts")
    clean["permissionMode"] = "default"
    return clean


def read_profiles(root: Path) -> dict:
    profiles = {}
    for path in sorted(root.glob("*/*")):
        if not path.is_dir():
            continue
        safe_path(root, str(path.relative_to(root)))
        records = {}
        excluded = set()
        for f in sorted(path.glob("local_*.json")):
            safe_path(root, str(f.relative_to(root)))
            if not SESSION_RE.fullmatch(f.stem):
                raise ValueError("Invalid local session filename.")
            data = json.loads(f.read_bytes())
            if not isinstance(data, dict) or data.get("sessionId") != f.stem:
                raise ValueError("sessionId does not match the filename.")
            if data.get("sshConfig") is not None or data.get("wslConfig") is not None:
                excluded.add(f.stem)
                continue
            if not isinstance(data.get("cwd"), str) or not Path(data["cwd"]).is_absolute():
                raise ValueError("cwd must be a valid absolute path.")
            sid = data.get("cliSessionId")
            if not isinstance(sid, str) or not UUID_RE.fullmatch(sid):
                raise ValueError("Invalid cliSessionId.")
            records[f.stem] = data
        deleted = {"local_" + f.name[len("deleted_"):] for f in path.glob("deleted_*")}
        profiles[str(path.relative_to(root))] = {"records": records, "deleted": deleted, "excluded": excluded}
    if len(profiles) < 2:
        raise ValueError("At least two account/organization profiles are required.")
    return profiles


def catalogue_fingerprint(root: Path) -> str:
    entries = []
    for path in sorted(root.glob("*/*/*")):
        if path.name == "archived-sessions.idx" or path.name.startswith("deleted_") or (path.suffix == ".json" and SESSION_RE.fullmatch(path.stem)):
            relative = str(path.relative_to(root))
            safe_path(root, relative)
            entries.append((relative, file_hash(path)))
    return digest(json_bytes(entries))


def transcript_index(projects: Path) -> dict:
    index = {}
    for f in sorted(projects.glob("*/*.jsonl")):
        if is_link(f) or projects.resolve() not in f.resolve().parents:
            raise ValueError("Transcript must be inside the isolated copy.")
        assert_no_links(f)
        index.setdefault(f.stem, []).append(f)
    return index


def valid_transcript(path: Path) -> bool:
    """Accept main-session messages and a connected inherited prefix from a fork."""
    found_messages = False
    inherited = False
    inherited_uuids = set()
    linked_prefix = False
    try:
        with path.open("rb") as stream:
            for line in stream:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    return False
                if entry.get("type") in ("user", "assistant") and isinstance(entry.get("message"), dict):
                    sid = entry.get("sessionId")
                    if sid == path.stem:
                        found_messages = True
                        if entry.get("parentUuid") in inherited_uuids:
                            linked_prefix = True
                    else:
                        # Forked sessions can start with copied ancestor messages.
                        # A foreign suffix or an unrelated copied file is ambiguous.
                        if (found_messages or not isinstance(sid, str) or not UUID_RE.fullmatch(sid)
                                or not isinstance(entry.get("uuid"), str)
                                or not UUID_RE.fullmatch(entry["uuid"])):
                            return False
                        inherited = True
                        inherited_uuids.add(entry["uuid"])
    except (OSError, ValueError):
        return False
    return found_messages and (not inherited or linked_prefix)


def locate_transcript(record: dict, index: dict, valid_cache=None):
    if valid_cache is None:
        valid_cache = {}
    ids = [record["cliSessionId"], *reversed(record.get("priorCliSessionIds", []))]
    for sid in ids:
        matches = index.get(sid, [])
        if len(matches) == 1:
            path = matches[0]
            if path not in valid_cache:
                valid_cache[path] = valid_transcript(path)
            if valid_cache[path]:
                return path
            # A malformed current transcript must not silently use an older one.
            return None
        if len(matches) > 1:
            return None  # Same ID in different projects is ambiguous in Claude.
    return None


def build_plan(root: Path, projects: Path, *, resolve_conflicts=False, include_unavailable=False) -> dict:
    root, projects = Path(root), Path(projects)
    baseline = catalogue_fingerprint(root)
    profiles = read_profiles(root)
    index = transcript_index(projects)
    plan = {"version": 1, "root": str(root.resolve()), "catalog_sha256": baseline,
            "transcripts": [], "changes": [],
            "artifact_conflicts": [],
            "missing_transcripts": [], "conflicts": [], "resolved_conflicts": [], "tombstone_skips": [],
            "summary": {"accounts": len({Path(name).parts[0] for name in profiles}),
                        "profiles": len(profiles), "copies": 0, "updates": 0, "archive_indexes": 0}}
    all_ids = sorted({sid for p in profiles.values() for sid in p["records"]})
    missing = set()
    valid_cache = {}
    artifact_cache = {}
    required_transcripts = set()

    def add(relative, data, reason):
        path = safe_path(root, relative)
        payload = json_bytes(data)
        if path.exists() and path.read_bytes() == payload:
            return
        plan["changes"].append({"relative_path": relative,
                                "before_sha256": file_hash(path),
                                "data_b64": base64.b64encode(payload).decode(),
                                "reason": reason})

    for sid in all_ids:
        copies = [(name, p["records"][sid]) for name, p in profiles.items() if sid in p["records"]]
        all_copies = copies[:]
        variants = {digest(json_bytes(history_record(r))) for _, r in copies}
        if len(variants) != 1:
            def activity(item):
                value = item[1].get("lastActivityAt", 0)
                return value if isinstance(value, (int, float)) else 0
            newest = sorted(copies, key=activity, reverse=True)
            latest_activity = activity(newest[0])
            latest_variants = {digest(json_bytes(history_record(record)))
                               for name, record in newest
                               if activity((name, record)) == latest_activity}
            # Several accounts may already share the same newest history.
            # A tie is ambiguous only when those newest histories differ.
            if not resolve_conflicts or len(latest_variants) != 1:
                plan["conflicts"].append({"sessionId": sid, "profiles": [n for n, _ in copies]})
                continue
            copies = newest
            plan["resolved_conflicts"].append({"sessionId": sid, "source": newest[0][0], "lastActivityAt": activity(newest[0])})
        source = copies[0][1]
        shared_artifacts, artifact_conflicts, artifact_transcripts = reconcile_artifacts(
            all_copies, index, valid_cache, artifact_cache)
        required_transcripts.update(artifact_transcripts)
        for identifier in sorted(artifact_conflicts):
            plan["artifact_conflicts"].append({"sessionId": sid, "artifactId": identifier,
                                               "reason": "same_timestamp_different_metadata"})
        transcript = locate_transcript(source, index, valid_cache)
        if transcript is None:
            missing.add(sid)
            if not include_unavailable:
                continue
        for name, profile in profiles.items():
            if sid in profile["records"]:
                current = profile["records"][sid]
                record = dict(current)
                if history_record(current) != history_record(source):
                    # History advances; account-specific settings stay with the destination.
                    record = {k: v for k, v in current.items() if k not in PORTABLE_KEYS}
                    record.update({k: v for k, v in history_record(source).items() if k != "permissionMode"})
                    if "publishedArtifacts" in current:
                        record["publishedArtifacts"] = current["publishedArtifacts"]
                    if transcript is not None:
                        record.pop("transcriptUnavailable", None)
                record = with_artifacts(record, shared_artifacts, artifact_conflicts)
                if transcript is not None:
                    record.pop("transcriptUnavailable", None)
                if record != current:
                    add(f"{name}/{sid}.json", record, "update_session")
                    profile["records"][sid] = record
                    plan["summary"]["updates"] += 1
                    if transcript is not None:
                        required_transcripts.add(transcript)
                continue
            if sid in profile["excluded"]:
                plan["conflicts"].append({"sessionId": sid, "profiles": [copies[0][0], name], "reason": "remote_record_occupied"})
                continue
            if sid in profile["deleted"]:
                plan["tombstone_skips"].append({"sessionId": sid, "profile": name})
                continue
            record = with_artifacts(history_record(source), shared_artifacts, set())
            if transcript is None:
                record["transcriptUnavailable"] = True
            # Normalize comparison to keep a second run idempotent even for stale flags.
            add(f"{name}/{sid}.json", record, "copy_session")
            profile["records"][sid] = record
            plan["summary"]["copies"] += 1
            if transcript is not None:
                required_transcripts.add(transcript)

    plan["missing_transcripts"] = sorted(missing)
    for name, profile in profiles.items():
        idxpath = safe_path(root, f"{name}/archived-sessions.idx")
        existing = {"v": 1, "archived": []}
        if idxpath.exists():
            existing = json.loads(idxpath.read_bytes())
            if (not isinstance(existing, dict) or existing.get("v") != 1
                    or not isinstance(existing.get("archived"), list)
                    or any(not isinstance(s, str) for s in existing["archived"])):
                raise ValueError("Unrecognized archived-session index format.")
        # Preserve hints for archived sessions not yet loaded into JSON records.
        archived = set(existing["archived"])
        for sid, rec in profile["records"].items():
            if rec.get("isArchived", False):
                archived.add(sid)
            else:
                archived.discard(sid)
        archived.difference_update(profile["deleted"])
        chosen = {**existing, "archived": sorted(archived)}
        if existing != chosen:
            add(f"{name}/archived-sessions.idx", chosen, "archive_index")
            plan["summary"]["archive_indexes"] += 1
    plan["summary"].update({"missing_transcripts": len(missing),
                            "artifact_conflicts": len(plan["artifact_conflicts"]),
                            "conflicts": len(plan["conflicts"]),
                            "resolved_conflicts": len(plan["resolved_conflicts"]),
                            "tombstone_skips": len(plan["tombstone_skips"]),
                            "writes": len(plan["changes"])})
    plan["transcripts"] = [{"path": str(p.resolve()), "sha256": file_hash(p)} for p in sorted(required_transcripts)]
    if catalogue_fingerprint(root) != baseline:
        raise RuntimeError("The catalogue changed during the preview. Try again.")
    return plan


def preflight(root: Path, changes: list, after=False):
    seen = set()
    checked = []
    for change in changes:
        relative = change["relative_path"]
        if relative in seen:
            raise ValueError("Duplicate file in the plan.")
        seen.add(relative)
        path = safe_path(root, relative)
        if path.name != "archived-sessions.idx" and (path.suffix != ".json" or not SESSION_RE.fullmatch(path.stem)):
            raise ValueError("The plan contains a file outside the chat catalogue.")
        if len(Path(relative).parts) != 3:
            raise ValueError("Invalid catalogue structure.")
        expected = change["after_sha256"] if after else change["before_sha256"]
        if file_hash(path) != expected:
            raise RuntimeError("The catalogue changed after the preview. Generate a new plan.")
        data = None if after else base64.b64decode(change["data_b64"], validate=True)
        if not after:
            obj = json.loads(data)
            if not isinstance(obj, dict):
                raise ValueError("Invalid record in the plan.")
            if path.name == "archived-sessions.idx":
                if (obj.get("v") != 1 or not isinstance(obj.get("archived"), list)
                        or any(not isinstance(s, str) for s in obj["archived"])):
                    raise ValueError("Invalid index in the plan.")
            else:
                if "publishedArtifacts" in obj:
                    if (not isinstance(obj["publishedArtifacts"], list)
                            or len(obj["publishedArtifacts"]) > 50
                            or obj["publishedArtifacts"] != clean_artifacts(obj)):
                        raise ValueError("Invalid artifact reference in the plan.")
                existing = json.loads(path.read_bytes()) if path.exists() else {}
                expected_nonportable = {k: v for k, v in existing.items() if k not in PORTABLE_KEYS}
                actual_nonportable = {k: v for k, v in obj.items() if k not in PORTABLE_KEYS}
                # New imports carry only defaults, existing account-specific settings are preserved.
                if change.get("reason") == "copy_session":
                    allowed_nonportable = {"permissionMode": "default"}
                    if obj.get("transcriptUnavailable") is True:
                        allowed_nonportable["transcriptUnavailable"] = True
                else:
                    allowed_nonportable = expected_nonportable.copy()
                    if "transcriptUnavailable" not in actual_nonportable:
                        allowed_nonportable.pop("transcriptUnavailable", None)
                if (actual_nonportable != allowed_nonportable or obj.get("sessionId") != path.stem
                    or not isinstance(obj.get("cliSessionId"), str) or not UUID_RE.fullmatch(obj["cliSessionId"])
                    or not isinstance(obj.get("cwd"), str) or not Path(obj["cwd"]).is_absolute()):
                    raise ValueError("Import record is invalid or contains new access fields.")
        checked.append((change, path, data))
    return checked


def apply_plan(root: Path, plan: dict, backup_dir: Path, *, live=False):
    root = Path(root)
    with live_write_scope(root, plan["changes"], live):
        return _apply_plan(root, plan, backup_dir, live=live)


def _apply_plan(root: Path, plan: dict, backup_dir: Path, *, live=False):
    root, backup_dir = Path(root), Path(backup_dir)
    assert_test_root(root)
    assert_test_root(backup_dir)
    if plan.get("version") != 1 or plan.get("root") != str(root.resolve()):
        raise ValueError("The plan belongs to a different root or version.")
    def unchanged():
        if catalogue_fingerprint(root) != plan.get("catalog_sha256"):
            raise RuntimeError("The catalogue changed after the preview. Generate a new plan.")
        for transcript in plan.get("transcripts", []):
            if file_hash(Path(transcript["path"])) != transcript["sha256"]:
                raise RuntimeError("The transcript changed after the preview. Generate a new plan.")
        for asset in plan.get("asset_files", []):
            if safe_asset_hash(Path(asset["path"])) != asset["sha256"]:
                raise RuntimeError("A linked file changed after verification. Generate a new plan.")
    unchanged()
    if backup_dir.exists() or root.resolve() == backup_dir.resolve() or root.resolve() in backup_dir.resolve().parents:
        raise ValueError("Backup must be a new directory outside the catalogue.")
    checked = preflight(root, plan["changes"])
    manifest = {"version": 1, "root": str(root.resolve()), "state": "prepared", "changes": []}
    private_dir(backup_dir)
    for change, path, data in checked:
        entry = {"relative_path": change["relative_path"],
                 "before_sha256": change["before_sha256"], "after_sha256": digest(data)}
        if path.exists():
            target = safe_path(backup_dir / "before", change["relative_path"])
            atomic_write(target, path.read_bytes())
        manifest["changes"].append(entry)
    atomic_write(backup_dir / "manifest.json", json_bytes(manifest))
    written = []
    try:
        # Preflight again after backup; no writes occur if a source changed meanwhile.
        unchanged()
        preflight(root, plan["changes"])
        if live:
            assert_claude_closed()
        for change, path, data in checked:
            atomic_write(path, data)
            written.append((change, path))
        manifest["state"] = "applied"
        atomic_write(backup_dir / "manifest.json", json_bytes(manifest))
    except BaseException:
        for change, path in reversed(written):
            if change["before_sha256"] is None:
                path.unlink()
            else:
                atomic_write(path, (backup_dir / "before" / change["relative_path"]).read_bytes())
        manifest["state"] = "rolled_back"
        atomic_write(backup_dir / "manifest.json", json_bytes(manifest))
        raise
    return manifest


def undo(root: Path, backup_dir: Path, *, live=False):
    root, backup_dir = Path(root), Path(backup_dir)
    manifest = json.loads((backup_dir / "manifest.json").read_bytes())
    with live_write_scope(root, manifest["changes"], live):
        return _undo(root, backup_dir, live=live)


def _undo(root: Path, backup_dir: Path, *, live=False):
    root, backup_dir = Path(root), Path(backup_dir)
    assert_test_root(root)
    assert_test_root(backup_dir)
    manifest = json.loads((backup_dir / "manifest.json").read_bytes())
    if manifest.get("version") != 1 or manifest.get("root") != str(root.resolve()) or manifest.get("state") != "applied":
        raise ValueError("Backup does not match an active application in this root.")
    checked = preflight(root, manifest["changes"], after=True)
    for change, _, _ in checked:
        if change["before_sha256"] is not None:
            saved = safe_path(backup_dir / "before", change["relative_path"])
            if file_hash(saved) != change["before_sha256"]:
                raise RuntimeError("Backup is incomplete or changed. No files were restored.")
    # Keep post-sync bytes so a failed restore can return to the applied state.
    post_sync = {str(path): path.read_bytes() for _, path, _ in checked}
    restored = []
    try:
        if live:
            assert_claude_closed()
        for change, path, _ in checked:
            if change["before_sha256"] is None:
                path.unlink()
            else:
                atomic_write(path, (backup_dir / "before" / change["relative_path"]).read_bytes())
            restored.append(path)
        manifest["state"] = "undone"
        atomic_write(backup_dir / "manifest.json", json_bytes(manifest))
    except BaseException:
        for path in reversed(restored):
            atomic_write(path, post_sync[str(path)])
        raise
    return {"restored": len(checked)}


def create_sandbox(dest: Path) -> dict:
    dest = Path(dest).absolute()
    assert_test_root(dest)
    if dest.exists():
        raise ValueError("Choose a new directory for the test copy.")
    private_dir(dest)
    registry = dest / "registry"
    projects = dest / "config/projects"
    private_dir(registry)
    private_dir(projects)
    snapshot = []

    def copy_file(source, target):
        if is_link(source):
            raise ValueError("The test copy does not follow symbolic links.")
        assert_no_links(source)
        stat_before = source.stat()
        private_dir(target.parent)
        shutil.copyfile(source, target)
        target.chmod(0o600)
        stat_after = source.stat()
        if (stat_before.st_size, stat_before.st_mtime_ns) != (stat_after.st_size, stat_after.st_mtime_ns):
            raise RuntimeError("Claude updated a file during copying. Create another copy.")
        sha = file_hash(target)
        if file_hash(source) != sha:
            raise RuntimeError("Inconsistent copy; try again when the session is idle.")
        snapshot.append({"source": str(source), "copy": str(target.relative_to(dest)), "sha256": sha})

    profile_dirs = sorted(p for p in LIVE_ROOT.glob("*/*") if p.is_dir())
    for i, p in enumerate(profile_dirs):
        target = registry / f"account-{i+1}" / "org-local"
        private_dir(target)
        for f in sorted(p.iterdir()):
            if f.is_file() and (SESSION_RE.fullmatch(f.stem) and f.suffix == ".json"
                                or f.name == "archived-sessions.idx" or f.name.startswith("deleted_")):
                copy_file(f, target / f.name)
    for project in sorted(p for p in LIVE_PROJECTS.iterdir() if p.is_dir()):
        for transcript in sorted(project.glob("*.jsonl")):
            copy_file(transcript, projects / project.name / transcript.name)
            artifacts = project / transcript.stem
            if artifacts.is_dir():
                for f in sorted(artifacts.rglob("*")):
                    if f.is_file():
                        copy_file(f, projects / f.relative_to(LIVE_PROJECTS))
    manifest = {"version": 1, "files": snapshot, "profiles": len(profile_dirs),
                "registry": str(registry), "config": str(dest / "config")}
    atomic_write(dest / "snapshot.json", json_bytes(manifest))
    return {"sandbox": str(dest), "profiles": len(profile_dirs), "files_copied": len(snapshot),
            "bytes_copied": sum((dest / e["copy"]).stat().st_size for e in snapshot)}


@contextmanager
def sync_lock():
    lock_dir = sync_platform.sync_storage_directory()
    assert_test_root(lock_dir)
    private_dir(lock_dir)
    lock_path = lock_dir / "sync.lock"
    with lock_path.open("a+b") as handle:
        lock_path.chmod(0o600)
        try:
            sync_platform.lock_file(handle)
        except BlockingIOError as error:
            raise RuntimeError("Another synchronization is already running. Wait for it to finish.") from error
        try:
            yield
        finally:
            sync_platform.unlock_file(handle)


def sync_accounts(storage_dir: Path | None = None) -> dict:
    assert_claude_closed()
    storage = storage_dir or Path(__file__).resolve().parent / ".sandbox"
    assert_test_root(storage)
    with sync_lock():
        operation = storage / ("sync-" + uuid.uuid4().hex[:12])
        private_dir(operation)
        plan = build_plan(LIVE_ROOT, LIVE_PROJECTS, resolve_conflicts=True, include_unavailable=True)
        profiles_before = read_profiles(LIVE_ROOT)
        audit_records = [r for profile in profiles_before.values() for r in profile["records"].values()]
        audit_records.extend(json.loads(base64.b64decode(change["data_b64"]))
                             for change in plan["changes"]
                             if change.get("reason") in ("copy_session", "update_session"))
        assets = audit_assets(audit_records, LIVE_PROJECTS, backup_dir=operation / "asset-snapshot")
        prior_reports = []
        candidates = sorted(storage.glob("sync-*/backup/asset-manifest.json"),
                            key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in candidates:
            safe_path(storage, str(path.relative_to(storage)))
            try:
                report = json.loads(path.read_bytes())
                if isinstance(report, dict) and isinstance(report.get("entries"), list):
                    prior_reports.append(report)
            except (OSError, ValueError):
                continue
        recover_preserved_outputs(assets, prior_reports, operation / "asset-snapshot")
        assets["summary"]["artifact_conflicts"] = len(plan["artifact_conflicts"])
        assets["artifact_conflicts"] = plan["artifact_conflicts"]
        plan["asset_files"] = [{"path": entry["path"], "sha256": entry["sha256"]}
                               for entry in assets["entries"] if entry.get("status") == "available"]
        atomic_write(operation / "asset-manifest.json", json_bytes(assets))
        atomic_write(operation / "plan.json", json_bytes(plan))
        snapshot = []
        for source in sorted(LIVE_ROOT.glob("*/*/*")):
            if source.is_file() and (source.name == "archived-sessions.idx" or source.name.startswith("deleted_")
                                    or source.suffix == ".json" and SESSION_RE.fullmatch(source.stem)):
                relative = str(source.relative_to(LIVE_ROOT))
                safe_path(LIVE_ROOT, relative)
                target = safe_path(operation / "full-catalogue", relative)
                atomic_write(target, source.read_bytes())
                snapshot.append({"relative_path": relative, "sha256": file_hash(target)})
        atomic_write(operation / "snapshot.json", json_bytes(snapshot))
        manifest = apply_plan(LIVE_ROOT, plan, operation / "backup", live=True)
        atomic_write(operation / "backup/asset-manifest.json", json_bytes(assets))
        profiles = read_profiles(LIVE_ROOT)
        records = {sid: r for profile in profiles.values() for sid, r in profile["records"].items()}
        result = {**plan["summary"], "files_written": len(manifest["changes"]),
                  "chats": len(records), "projects": len({r.get("originCwd", r["cwd"]) for r in records.values()}),
                  "assets": assets["summary"],
                  "backup": str(operation / "backup")}
        atomic_write(operation / "result.json", json_bytes(result))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-data", type=Path,
                        help="Claude application data directory containing claude-code-sessions.")
    parser.add_argument("--projects-dir", type=Path,
                        help="Shared transcript directory (default: ~/.claude/projects).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sync", help="Sync all local-account projects with an automatic backup.")
    p.add_argument("--live", action="store_true", required=True)
    p.add_argument("--storage-dir", type=Path, help="Private directory for application backups.")
    p = sub.add_parser("audit", help="Check artifacts and images without changing the catalogue.")
    p.add_argument("--root", type=Path)
    p.add_argument("--projects", type=Path)
    p.add_argument("--out", type=Path, required=True, help="Private manifest of discovered files.")
    p = sub.add_parser("sandbox")
    p.add_argument("--dest", type=Path, required=True)
    p = sub.add_parser("plan")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--projects", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--all-chats", action="store_true", help="Also mirror records without a readable local transcript.")
    p.add_argument("--resolve-newest", action="store_true", help="Resolve conflicts using the latest activity; ties remain pending.")
    p = sub.add_parser("apply")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--live", action="store_true", help="Apply to the live catalogue only while Claude is closed.")
    p = sub.add_parser("undo")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--live", action="store_true")
    args = parser.parse_args()
    try:
        configure_live_paths(args.app_data, args.projects_dir)
        if args.command == "audit":
            args.root = args.root if args.root is not None else LIVE_ROOT
            args.projects = args.projects if args.projects is not None else LIVE_PROJECTS
        if args.command == "sync":
            result = sync_accounts(args.storage_dir)
        elif args.command == "audit":
            profiles = read_profiles(args.root)
            records = [r for profile in profiles.values() for r in profile["records"].values()]
            report = audit_assets(records, args.projects)
            atomic_write(args.out, json_bytes(report))
            result = {**report["summary"], "manifest": str(args.out)}
        elif args.command == "sandbox":
            result = create_sandbox(args.dest)
        elif args.command == "plan":
            plan = build_plan(args.root, args.projects, resolve_conflicts=args.resolve_newest, include_unavailable=args.all_chats)
            atomic_write(args.out, json_bytes(plan))
            result = {**plan["summary"], "plan": str(args.out)}
        elif args.command == "apply":
            manifest = apply_plan(args.root, json.loads(args.plan.read_bytes()), args.backup, live=args.live)
            result = {"writes": len(manifest["changes"]), "backup": str(args.backup)}
        else:
            result = undo(args.root, args.backup, live=args.live)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, RuntimeError) as e:
        parser.exit(1, f"Error: {e}\n")


if __name__ == "__main__":
    main()
