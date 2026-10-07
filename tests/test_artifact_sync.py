import base64
import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import claude_sync as sync
from tests.support import create_symlink


class ArtifactSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / "claude-app" / "registry"
        self.projects = self.base / "projects"
        self.profiles = [self.root / account / "org" for account in ("a", "b", "c")]
        for profile in self.profiles:
            profile.mkdir(parents=True)
        self.cli = str(uuid.uuid4())
        self.sid = "local_" + str(uuid.uuid4())
        self.record = {"sessionId": self.sid, "cliSessionId": self.cli,
                       "cwd": str(self.base / "work"), "lastActivityAt": 100,
                       "title": "Synthetic", "permissionMode": "plan"}
        directory = self.projects / "synthetic"
        directory.mkdir(parents=True)
        self.transcript = directory / (self.cli + ".jsonl")
        self.transcript.write_text(json.dumps({"type": "user", "sessionId": self.cli,
                                               "message": {"role": "user", "content": "Synthetic"}}) + "\n")
        self.artifact = {"url": "https://claude.ai/code/artifact/" + str(uuid.uuid4()),
                         "title": "Synthetic artifact", "sourcePath": str(self.base / "work/page.html"),
                         "updatedAt": 1000}

    def put(self, index, **fields):
        record = {**self.record, **fields}
        (self.profiles[index] / (self.sid + ".json")).write_bytes(sync.json_bytes(record))
        return record

    def get(self, index):
        return json.loads((self.profiles[index] / (self.sid + ".json")).read_bytes())

    def plan(self):
        return sync.build_plan(self.root, self.projects, resolve_conflicts=True, include_unavailable=True)

    def apply(self, plan):
        return sync.apply_plan(self.root, plan, self.base / "backup")

    def test_preserves_artifacts_and_repairs_previously_sanitized_copies(self):
        self.put(0, publishedArtifacts=[self.artifact], remoteMcpServersConfig=[{"name": "private"}])
        self.put(1)
        plan = self.plan()
        self.assertEqual(plan["summary"]["conflicts"], 0)
        self.assertEqual(plan["summary"]["updates"], 1)
        self.assertEqual(plan["summary"]["copies"], 1)
        self.apply(plan)
        for index in range(3):
            self.assertEqual(self.get(index)["publishedArtifacts"], [self.artifact])
        self.assertEqual(self.get(1)["permissionMode"], "plan")
        self.assertEqual(self.get(2)["permissionMode"], "default")
        self.assertNotIn("remoteMcpServersConfig", self.get(2))
        self.assertEqual(self.plan()["changes"], [])
        sync.undo(self.root, self.base / "backup")
        self.assertNotIn("publishedArtifacts", self.get(1))
        self.assertFalse((self.profiles[2] / (self.sid + ".json")).exists())

    def test_newest_history_does_not_erase_older_artifact_discoveries(self):
        self.put(0, publishedArtifacts=[self.artifact])
        self.put(1, lastActivityAt=200)
        self.apply(self.plan())
        for index in range(3):
            self.assertEqual(self.get(index)["lastActivityAt"], 200)
            self.assertEqual(self.get(index)["publishedArtifacts"], [self.artifact])

    def test_artifacts_from_different_accounts_are_unioned(self):
        other = {**self.artifact, "url": "https://claude.com/artifact/" + str(uuid.uuid4()), "updatedAt": 2000}
        self.put(0, publishedArtifacts=[self.artifact])
        self.put(1, publishedArtifacts=[other])
        self.apply(self.plan())
        for index in range(3):
            self.assertEqual(self.get(index)["publishedArtifacts"], [other, self.artifact])
        self.assertEqual(self.plan()["changes"], [])

    def test_latest_artifact_version_is_selected_independently_of_chat_activity(self):
        newest = {**self.artifact, "title": "Updated", "updatedAt": 2000}
        self.put(0, publishedArtifacts=[self.artifact], lastActivityAt=200)
        self.put(1, publishedArtifacts=[newest])
        self.apply(self.plan())
        for index in range(3):
            self.assertEqual(self.get(index)["publishedArtifacts"], [newest])

    def test_equal_timestamp_artifact_conflicts_preserve_existing_versions(self):
        other = {**self.artifact, "title": "Different"}
        self.put(0, publishedArtifacts=[self.artifact])
        self.put(1, publishedArtifacts=[other])
        plan = self.plan()
        self.assertEqual(plan["summary"]["conflicts"], 0)
        self.assertEqual(plan["summary"]["artifact_conflicts"], 1)
        self.apply(plan)
        self.assertEqual(self.get(0)["publishedArtifacts"], [self.artifact])
        self.assertEqual(self.get(1)["publishedArtifacts"], [other])
        self.assertNotIn("publishedArtifacts", self.get(2))
        self.assertEqual(self.plan()["changes"], [])

    def test_frame_link_repairs_missing_catalogue_metadata(self):
        self.put(0)
        event = {"type": "frame-link", "frameUrl": self.artifact["url"],
                 "path": self.artifact["sourcePath"], "title": self.artifact["title"],
                 "timestamp": "2026-10-03T12:00:00Z"}
        with self.transcript.open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        self.apply(self.plan())
        for index in range(3):
            actual = self.get(index)["publishedArtifacts"][0]
            self.assertEqual(actual["url"], self.artifact["url"])
            self.assertEqual(actual["sourcePath"], self.artifact["sourcePath"])
            self.assertGreater(actual["updatedAt"], 0)
        self.assertEqual(self.plan()["changes"], [])

    def test_metadata_artifacts_and_prior_transcripts_can_repair_metadata(self):
        prior = str(uuid.uuid4())
        self.put(0, priorCliSessionIds=[prior])
        path = self.transcript.parent / (prior + ".jsonl")
        path.write_text(json.dumps({"type": "user", "sessionId": prior,
            "message": {"role": "user", "content": "Synthetic"},
            "metadata": {"artifacts": [{"url": self.artifact["url"], "title": "Recovered",
                                          "updated_at": "2026-10-03T12:00:00Z"}]}}) + "\n")
        self.apply(self.plan())
        self.assertEqual(self.get(2)["publishedArtifacts"][0]["title"], "Recovered")

    def test_deleted_destination_is_not_resurrected_for_artifact_repair(self):
        self.put(0, publishedArtifacts=[self.artifact])
        (self.profiles[2] / self.sid.replace("local_", "deleted_", 1)).touch()
        self.apply(self.plan())
        self.assertFalse((self.profiles[2] / (self.sid + ".json")).exists())

    def test_injected_artifact_urls_or_unknown_fields_are_rejected_before_writes(self):
        for url in ("https://attacker.invalid/artifact/" + str(uuid.uuid4()), "file:///secret"):
            self.put(0, publishedArtifacts=[self.artifact])
            plan = self.plan()
            change = next(c for c in plan["changes"] if c["reason"] == "copy_session")
            record = json.loads(base64.b64decode(change["data_b64"]))
            record["publishedArtifacts"][0]["url"] = url
            change["data_b64"] = base64.b64encode(sync.json_bytes(record)).decode()
            with self.assertRaises(ValueError):
                self.apply(plan)
            self.assertFalse((self.base / "backup").exists())

    def test_changed_recovery_transcript_invalidates_plan(self):
        self.put(0, publishedArtifacts=[self.artifact])
        plan = self.plan()
        with self.transcript.open("a") as stream:
            stream.write(json.dumps({"type": "frame-link", "frameUrl": self.artifact["url"]}) + "\n")
        with self.assertRaises(RuntimeError):
            self.apply(plan)

    def test_linked_file_change_or_symlink_swap_invalidates_plan(self):
        self.put(0)
        path = self.base / "image.png"
        path.write_bytes(b"first")
        plan = self.plan()
        plan["asset_files"] = [{"path": str(path), "sha256": sync.file_hash(path)}]
        path.write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            self.apply(plan)
        target = self.base / "target.png"
        target.write_bytes(b"first")
        path.unlink()
        create_symlink(self, path, target)
        with self.assertRaises((RuntimeError, ValueError, OSError)):
            self.apply(plan)
        self.assertFalse((self.base / "backup").exists())

    def test_desktop_sync_backs_up_linked_files_and_reports_assets(self):
        path = Path(self.artifact["sourcePath"])
        path.parent.mkdir()
        path.write_bytes(b"<html>synthetic</html>")
        self.put(0, publishedArtifacts=[self.artifact])
        with patch.object(sync, "LIVE_ROOT", self.root), patch.object(sync, "LIVE_PROJECTS", self.projects), \
                patch.object(sync, "LIVE_APP_DATA", self.root.parent), patch.object(sync, "assert_claude_closed"), \
                patch.object(sync, "sync_lock", return_value=contextlib.nullcontext()):
            result = sync.sync_accounts(self.base / "storage")
        self.assertEqual(result["assets"]["artifact_references"], 1)
        self.assertEqual(result["assets"]["local_files"], 1)
        manifest = json.loads((Path(result["backup"]) / "asset-manifest.json").read_bytes())
        entry = next(e for e in manifest["entries"] if e.get("path") == str(path.resolve()))
        self.assertEqual(Path(entry["backup_path"]).read_bytes(), path.read_bytes())
        self.assertEqual(path.read_bytes(), b"<html>synthetic</html>")

    def test_later_sync_keeps_verified_output_after_original_temporary_file_disappears(self):
        path = Path(self.artifact["sourcePath"])
        path.parent.mkdir()
        payload = b"<html>preserved output</html>"
        path.write_bytes(payload)
        self.put(0, publishedArtifacts=[self.artifact])
        with patch.object(sync, "LIVE_ROOT", self.root), patch.object(sync, "LIVE_PROJECTS", self.projects), \
                patch.object(sync, "LIVE_APP_DATA", self.root.parent), patch.object(sync, "assert_claude_closed"), \
                patch.object(sync, "sync_lock", return_value=contextlib.nullcontext()):
            first = sync.sync_accounts(self.base / "storage")
            path.unlink()
            second = sync.sync_accounts(self.base / "storage")
            third = sync.sync_accounts(self.base / "storage")
        self.assertEqual(first["assets"]["local_files"], 1)
        for result in (second, third):
            self.assertEqual(result["assets"]["missing_output_files"], 1)
            self.assertEqual(result["assets"]["preserved_output_files"], 1)
            self.assertEqual(result["assets"]["unpreserved_output_files"], 0)
            report = json.loads((Path(result["backup"]) / "asset-manifest.json").read_bytes())
            entry = next(e for e in report["entries"] if e.get("path") == str(path.resolve()))
            self.assertEqual(Path(entry["output_path"]).suffix, ".html")
            self.assertEqual(Path(entry["output_path"]).read_bytes(), payload)
        self.assertFalse(path.exists())


class ArtifactURLTests(unittest.TestCase):
    def test_source_paths_are_not_truncated_into_other_files(self):
        value = {"url": "https://claude.ai/artifact/" + str(uuid.uuid4()),
                 "title": "t" * 150, "sourcePath": "/" + "a" * 4096, "updatedAt": 1e30}
        clean = sync.clean_artifact(value)
        self.assertEqual(len(clean["title"]), 120)
        self.assertNotIn("sourcePath", clean)
        self.assertNotIn("updatedAt", clean)
        self.assertIsNotNone(sync.artifact_identity(value["url"].replace("claude.ai", "CLAUDE.AI")))
        self.assertIsNotNone(sync.artifact_identity(value["url"].replace("claude.ai", "CLAUDE.AI:443")))

    def test_uuid_frame_slug_and_vanity_urls_share_identity(self):
        identifier = str(uuid.uuid4())
        self.assertEqual(sync.artifact_identity("https://claude.ai/code/frame/" + identifier), identifier)
        self.assertEqual(sync.artifact_identity("https://claude.com/artifact/title-" + identifier + "?v=2#view"), identifier)
        number = uuid.UUID(identifier).int
        encoded = ""
        while number:
            number, remainder = divmod(number, 58)
            encoded = sync.BASE58_ALPHABET[remainder] + encoded
        encoded = encoded.rjust(22, "1")
        self.assertEqual(sync.artifact_identity("https://claude.ai/artifact/" + encoded), identifier)

    def test_invalid_domains_credentials_ports_ids_and_design_pages_are_rejected(self):
        identifier = str(uuid.uuid4())
        for url in ("http://claude.ai/artifact/" + identifier,
                    "https://claude.ai.evil.invalid/artifact/" + identifier,
                    "https://user:pass@claude.ai/artifact/" + identifier,
                    "https://claude.ai:444/artifact/" + identifier,
                    "https://claude.ai/design/p/" + identifier,
                    "https://claude.ai/artifact/" + "z" * 22,
                    "https://claude.ai/artifact/not-an-id"):
            with self.subTest(url=url):
                self.assertIsNone(sync.artifact_identity(url))


if __name__ == "__main__":
    unittest.main()
