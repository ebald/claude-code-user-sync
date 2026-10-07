"""Inspect local transcript assets without changing transcripts or source files.

Only explicit attachment, artifact and Markdown references are considered. The
returned manifest is private metadata: it never includes message text or image
payloads. External links are recorded, never downloaded.
"""
from __future__ import annotations

import base64
import binascii
import errno
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import uuid
from urllib.parse import unquote, urlsplit


_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp", ".tif", ".tiff", ".heic"}
_MARKDOWN_LINK = re.compile(r"(!?)\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|((?:[^\s()]|\([^()\n]*\))+))(?:\s+[\"'][^\n]*?[\"'])?\s*\)")
_GENERATED_PATH = re.compile(r"`((?:/|[A-Za-z]:[\\/]|\./|\.\./)[^`\n]+\.(?:png|jpe?g|gif|webp|avif|svg))`", re.I)
_GENERATED_TOOL = re.compile(r"(?:imagegen|generate_image|edit_image)", re.I)
_CHUNK_SIZE = 1024 * 1024
_MACOS_ROOT_ALIASES = {"var": "/private/var", "tmp": "/private/tmp", "etc": "/private/etc"}


class UnsafeAssetError(ValueError):
    """A reference is not a regular file reached without symlinks."""


def _absolute(path: Path) -> Path:
    if os.name == "nt":
        _validate_windows_components(Path(path))
    path = Path(os.path.abspath(os.fspath(path)))
    # macOS's OS-owned root aliases are the same storage location. Canonicalize
    # only their exact known targets; arbitrary attachment symlinks stay unsafe.
    if len(path.parts) > 1 and path.parts[1] in _MACOS_ROOT_ALIASES:
        alias = path.anchor + path.parts[1]
        target = _MACOS_ROOT_ALIASES[path.parts[1]]
        try:
            if os.readlink(alias) in (target, target.lstrip("/")):
                path = Path(target).joinpath(*path.parts[2:])
        except OSError:
            pass
    return path


def is_link(path: Path) -> bool:
    """Reject symlinks and every Windows reparse point, including junctions."""
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def assert_no_links(path: Path):
    """Check existing path components without following links or junctions."""
    path = _absolute(Path(path))
    current = Path(path.anchor)
    for component in (None, *path.parts[1:]):
        if component is not None:
            current /= component
        if is_link(current):
            raise UnsafeAssetError("symlink_or_reparse_point")


class _WindowsDirectory:
    """Keep all ancestors open to prevent renaming or changing reparse tags."""
    def __init__(self, path):
        self.path = path
        self.handles = []

    def close(self):
        api = _windows_api()
        for handle in reversed(self.handles):
            api.CloseHandle(handle)
        self.handles.clear()


def _windows_api():
    # Load only on Windows: ctypes.WinDLL and msvcrt are unavailable on macOS.
    import ctypes
    from ctypes import wintypes

    if not hasattr(_windows_api, "library"):
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = (wintypes.HANDLE,)
        api.CloseHandle.restype = wintypes.BOOL
        api.GetFileInformationByHandleEx.argtypes = (wintypes.HANDLE, ctypes.c_int,
                                                    wintypes.LPVOID, wintypes.DWORD)
        api.GetFileInformationByHandleEx.restype = wintypes.BOOL
        api.GetFileType.argtypes = (wintypes.HANDLE,)
        api.GetFileType.restype = wintypes.DWORD
        _windows_api.library = api
    return _windows_api.library


def _validate_windows_components(path: Path):
    """Reject lexical aliases before Windows normalization can erase them."""
    if path.drive and (not re.fullmatch(r"[A-Za-z]:", path.drive) or not path.root):
        raise UnsafeAssetError("unsupported_windows_path")
    components = path.parts[1:] if path.anchor else path.parts
    for component in components:
        if component in (".", ".."):
            continue
        stem = component.split(".", 1)[0].rstrip(" ").upper()
        if (re.search(r'[<>:"|?*\x00-\x1f]', component) or component.endswith((".", " "))
                or stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                or re.fullmatch(r"(?:COM|LPT)[1-9\u00b9\u00b2\u00b3]", stem)):
            raise UnsafeAssetError("unsupported_windows_path")


def _windows_path(path: Path) -> str:
    """Use an unambiguous local drive path; never open devices, shares or ADS."""
    _validate_windows_components(Path(path))
    path = _absolute(path)
    if not re.fullmatch(r"[A-Za-z]:", path.drive) or not path.is_absolute():
        raise UnsafeAssetError("unsupported_windows_path")
    # Extended syntax supports backups beyond MAX_PATH after validation above.
    return "\\\\?\\" + str(path)


def _windows_check_handle(handle, *, directory):
    import ctypes
    from ctypes import wintypes

    class AttributeTag(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]

    api = _windows_api()
    info = AttributeTag()
    if not api.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if info.attributes & 0x400:
        raise UnsafeAssetError("symlink_or_reparse_point")
    if bool(info.attributes & 0x10) != directory or api.GetFileType(handle) != 1:
        raise UnsafeAssetError("symlink_or_non_directory" if directory else "not_regular_file")


def _windows_open(path, *, directory=False, create=False):
    import ctypes

    api = _windows_api()
    access = 0x80 if directory else 0x40000080 if create else 0x80000000
    # Deny both writes and deletion for the lifetime of every checked handle.
    # Windows st_ctime is creation time, so stat fields alone cannot provide
    # the same evidence of concurrent changes as a POSIX metadata-change time.
    sharing = 1
    # Do not request recall of offline content before checking reparse tags.
    handle = api.CreateFileW(_windows_path(path), access, sharing, None,
                             1 if create else 3, 0x00200000 | 0x02000000 | 0x00100000, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        if code in (2, 3):
            raise FileNotFoundError(errno.ENOENT, "File or directory not found", str(path))
        raise ctypes.WinError(code)
    try:
        _windows_check_handle(handle, directory=directory)
    except BaseException:
        api.CloseHandle(handle)
        raise
    return handle


def _windows_open_directory(path, *, create=False):
    path = _absolute(path)
    _windows_path(path)
    directory = _WindowsDirectory(path)
    current = Path(path.anchor)
    try:
        directory.handles.append(_windows_open(current, directory=True))
        for component in path.parts[1:]:
            current /= component
            try:
                handle = _windows_open(current, directory=True)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(_windows_path(current), mode=0o700)
                except FileExistsError:
                    pass
                handle = _windows_open(current, directory=True)
            directory.handles.append(handle)
        return directory
    except BaseException:
        directory.close()
        raise


def _close_directory(directory):
    if isinstance(directory, _WindowsDirectory):
        directory.close()
    else:
        os.close(directory)


def _set_private_mode(fd, mode):
    # Windows uses inherited ACLs; Unix mode bits have no ACL meaning there.
    if os.name != "nt":
        os.fchmod(fd, mode)


def _directory_open_file(directory, name, *, create=False):
    if isinstance(directory, _WindowsDirectory):
        import msvcrt
        handle = _windows_open(directory.path / name, create=create)
        flags = (os.O_WRONLY if create else os.O_RDONLY) | os.O_BINARY
        try:
            return msvcrt.open_osfhandle(handle, flags)
        except BaseException:
            _windows_api().CloseHandle(handle)
            raise
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL if create else os.O_RDONLY | os.O_NONBLOCK
    try:
        fd = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafeAssetError("symlink_or_non_directory") from None
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise UnsafeAssetError("not_regular_file")
    return fd


def _directory_rename(directory, source, target):
    if isinstance(directory, _WindowsDirectory):
        os.rename(_windows_path(directory.path / source), _windows_path(directory.path / target))
    else:
        os.rename(source, target, src_dir_fd=directory, dst_dir_fd=directory)


def _directory_unlink(directory, name):
    if isinstance(directory, _WindowsDirectory):
        os.unlink(_windows_path(directory.path / name))
    else:
        os.unlink(name, dir_fd=directory)


@contextmanager
def _regular_stream(path):
    """Keep the checked parent directory guards alive for the entire read."""
    path = _absolute(Path(path))
    directory = _open_directory(path.parent)
    try:
        with os.fdopen(_directory_open_file(directory, path.name), "rb") as stream:
            yield stream
            if os.name == "nt":
                import msvcrt
                _windows_check_handle(msvcrt.get_osfhandle(stream.fileno()), directory=False)
    finally:
        _close_directory(directory)


def _image_signature_matches(data: bytes, media_type: str) -> bool:
    """Check supported image signatures, without claiming full image decoding."""
    if media_type == "image/png":
        return len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR"
    if media_type in ("image/jpeg", "image/jpg"):
        return len(data) >= 4 and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if media_type == "image/gif":
        return len(data) >= 10 and data[:6] in (b"GIF87a", b"GIF89a")
    if media_type == "image/webp":
        return len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return True


def _open_directory(path: Path, *, create=False, private=False):
    """Walk with directory descriptors so no component follows a symlink."""
    path = _absolute(path)
    if os.name == "nt":
        return _windows_open_directory(path, create=create)
    current = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            try:
                following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=current)
                except FileExistsError:
                    pass
                following = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = following
        if private:
            os.fchmod(current, 0o700)
        result, current = current, None
        return result
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENOTDIR):
            raise UnsafeAssetError("symlink_or_non_directory") from None
        raise
    finally:
        if current is not None:
            os.close(current)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _stream_hash(stream, output=None):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(_CHUNK_SIZE), b""):
        digest.update(block)
        if output is not None:
            output.write(block)
    return digest.hexdigest()


def _capture(path: Path, assets: Path | None = None, *, expected_sha256: str | None = None) -> dict:
    path = _absolute(path)
    with _regular_stream(path) as source:
        directory_fd = None
        temporary = None
        try:
            before = os.fstat(source.fileno())
            if assets is not None:
                directory_fd = _open_directory(assets, create=True, private=True)
                temporary = ".asset-" + uuid.uuid4().hex
                output_fd = _directory_open_file(directory_fd, temporary, create=True)
                with os.fdopen(output_fd, "wb") as output:
                    digest = _stream_hash(source, output)
                    output.flush()
                    os.fsync(output.fileno())
            else:
                digest = _stream_hash(source)
            after = os.fstat(source.fileno())
            if _identity(before) != _identity(after):
                raise RuntimeError("Asset file changed during verification.")
            try:
                with _regular_stream(path) as check:
                    if _identity(before) != _identity(os.fstat(check.fileno())):
                        raise RuntimeError("Asset file changed during verification.")
            except (OSError, UnsafeAssetError):
                raise RuntimeError("Asset file changed during verification.") from None
            if expected_sha256 is not None and digest != expected_sha256:
                raise RuntimeError("Asset backup does not match the expected contents.")
            result = {"sha256": digest, "bytes": before.st_size}
            if directory_fd is not None:
                # Existing snapshots must still match their content address.
                try:
                    existing_fd = _directory_open_file(directory_fd, digest)
                except FileNotFoundError:
                    _directory_rename(directory_fd, temporary, digest)
                    temporary = None
                else:
                    with os.fdopen(existing_fd, "rb") as existing:
                        if not stat.S_ISREG(os.fstat(existing.fileno()).st_mode) or _stream_hash(existing) != digest:
                            raise RuntimeError("Asset backup does not match the expected contents.")
                        _set_private_mode(existing.fileno(), 0o600)
                result["backup_path"] = str(assets / digest)
            return result
        except (OSError, UnsafeAssetError) as error:
            if assets is not None:
                raise RuntimeError("Could not create or verify the asset backup.") from error
            raise
        finally:
            if directory_fd is not None:
                try:
                    if temporary is not None:
                        _directory_unlink(directory_fd, temporary)
                except OSError as error:
                    raise RuntimeError("Could not remove the partial asset backup.") from error
                finally:
                    _close_directory(directory_fd)


def safe_asset_hash(path: Path) -> str:
    """Hash a stable regular file, refusing symlinks and concurrent changes."""
    return _capture(Path(path))["sha256"]


def _prepare_output(entry: dict, output_dir: Path) -> str:
    """Make a separate private copy retaining the original file extension."""
    path_identity = hashlib.sha256(entry["path"].encode()).hexdigest()[:12]
    name = Path(entry["path"]).name
    folder_name = name.encode("utf-8")[:96].decode("utf-8", errors="ignore")
    directory = output_dir / (folder_name + " - " + path_identity + "-" + entry["sha256"][:12])
    fd = None
    try:
        output_fd = _open_directory(output_dir, create=True, private=True)
        _close_directory(output_fd)
        copied = _capture(Path(entry["backup_path"]), directory, expected_sha256=entry["sha256"])
        if copied["sha256"] != entry["sha256"]:
            raise RuntimeError("Asset backup does not match the expected contents.")
        readable = directory / name
        fd = _open_directory(directory)
        try:
            existing_hash = safe_asset_hash(readable)
        except FileNotFoundError:
            _directory_rename(fd, copied["sha256"], name)
        else:
            if existing_hash != entry["sha256"]:
                raise RuntimeError("Output copy does not match the expected backup.")
            with _regular_stream(readable) as existing:
                _set_private_mode(existing.fileno(), 0o600)
            if name != copied["sha256"]:
                _directory_unlink(fd, copied["sha256"])
        return str(readable)
    except (OSError, UnsafeAssetError) as error:
        raise RuntimeError("Could not prepare the output files.") from error
    finally:
        if fd is not None:
            _close_directory(fd)


def _is_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except ValueError:
        return False


def recover_preserved_outputs(report: dict, prior_reports: list[dict], backup_dir: Path) -> dict:
    """Preserve proven older snapshots of missing outputs, never their originals.

    Previous manifests are ordered newest first. An exact normalized source
    path and verified SHA256 are required; filenames alone are insufficient.
    Missing status remains evidence about the live source even after recovery.
    """
    backup = _absolute(Path(backup_dir))
    available = {}
    for previous in prior_reports:
        for entry in previous.get("entries", []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                continue
            if entry.get("status") not in ("available", "cached") and not entry.get("preserved_from_backup"):
                continue
            if not isinstance(entry.get("backup_path"), str) or not isinstance(entry.get("sha256"), str):
                continue
            try:
                path = str(_absolute(Path(entry["path"])))
            except (ValueError, OSError):
                continue
            available.setdefault(path, []).append(entry)
    unavailable = report.setdefault("recovery_unavailable", [])
    evidence_keys = {(entry.get("path"), entry.get("backup_path"), entry.get("reason")) for entry in unavailable}

    def note(path, reason, candidate=None):
        entry = {"path": path, "reason": reason}
        if candidate is not None:
            entry["backup_path"] = candidate.get("backup_path")
        key = (entry["path"], entry.get("backup_path"), entry["reason"])
        if key not in evidence_keys:
            unavailable.append(entry)
            evidence_keys.add(key)

    summary = report.setdefault("summary", {})
    newly_prepared = 0
    for entry in report.get("entries", []):
        if entry.get("status") != "missing" or entry.get("scope") != "output" or not isinstance(entry.get("path"), str):
            continue
        path = str(_absolute(Path(entry["path"])))
        already_prepared = bool(entry.get("preserved_from_backup") and entry.get("output_path"))
        candidates = available.get(path, [])
        if entry.get("preserved_from_backup") and entry.get("backup_path") and entry.get("sha256"):
            candidates = [dict(entry), *candidates]
        for field in ("preserved_from_backup", "recovery_kind"):
            entry.pop(field, None)
        if not candidates:
            note(path, "no_previous_backup")
            continue
        for candidate in candidates:
            expected = candidate["sha256"]
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                note(path, "invalid_backup_hash", candidate)
                continue
            try:
                captured = _capture(Path(candidate["backup_path"]), backup / "assets", expected_sha256=expected)
            except FileNotFoundError:
                note(path, "previous_backup_not_found", candidate)
                continue
            except UnsafeAssetError:
                note(path, "previous_backup_unsafe", candidate)
                continue
            except OSError:
                note(path, "previous_backup_unreadable", candidate)
                continue
            entry.update(captured)
            entry["output_path"] = _prepare_output(entry, backup / "output-files")
            entry["preserved_from_backup"] = True
            entry["recovery_kind"] = "previous_backup"
            entry["recovery_source_path"] = str(_absolute(Path(candidate["backup_path"])))
            newly_prepared += not already_prepared
            break
    preserved = sum(entry.get("status") == "missing" and entry.get("scope") == "output" and bool(entry.get("preserved_from_backup"))
                    for entry in report.get("entries", []))
    summary["preserved_output_files"] = preserved
    summary["unpreserved_output_files"] = max(0, summary.get("missing_output_files", 0) - preserved)
    summary["prepared_output_files"] = summary.get("prepared_output_files", 0) + newly_prepared
    _carry_read_previews(report, prior_reports, backup)
    return report


def _carry_read_previews(report: dict, prior_reports: list[dict], backup: Path):
    """Keep already-associated Read previews separate from full original files."""
    previews = {}
    extensions = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
    for previous in prior_reports:
        for entry in previous.get("entries", []):
            if not isinstance(entry, dict):
                continue
            preview = entry.get("saved_read_preview")
            if isinstance(entry.get("path"), str) and isinstance(preview, dict):
                previews.setdefault(str(_absolute(Path(entry["path"]))), []).append(preview)
    for entry in report.get("entries", []):
        if entry.get("status") != "missing" or entry.get("scope") != "output" or not entry.get("path"):
            continue
        candidates = previews.get(str(_absolute(Path(entry["path"]))), [])
        if isinstance(entry.get("saved_read_preview"), dict):
            candidates = [entry["saved_read_preview"], *candidates]
        for preview in candidates:
            expected = preview.get("sha256", "")
            media_type = preview.get("media_type")
            source = preview.get("backup_path", preview.get("output_path"))
            if (preview.get("reason") != "saved_read_preview" or media_type not in extensions
                    or not isinstance(source, str) or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected)):
                continue
            try:
                captured = _capture(Path(source), backup / "assets", expected_sha256=expected)
            except (OSError, UnsafeAssetError):
                continue
            with _regular_stream(Path(captured["backup_path"])) as stream:
                if not _image_signature_matches(stream.read(), media_type):
                    raise RuntimeError("Preserved preview does not match the specified format.")
            path = Path(entry["path"])
            readable = {**captured, "path": str(path.with_name(path.stem + ".preview" + extensions[media_type]))}
            output_path = _prepare_output(readable, backup / "output-files/Recovered previews")
            entry["saved_read_preview"] = {**preview, **captured, "output_path": output_path}
            break
    report["summary"]["saved_read_images"] = sum(isinstance(e.get("saved_read_preview"), dict)
                                               for e in report.get("entries", []))


def audit_assets(records: list[dict], projects: Path, backup_dir: Path | None = None) -> dict:
    """Audit registered transcripts, completed outputs and historical links.

    Evidence remains private and complete. Diagnostics distinguish missing
    outputs from source-code citations, navigation and failed send attempts.
    """
    projects = _absolute(Path(projects))
    backup = _absolute(Path(backup_dir)) if backup_dir is not None else None
    assets = backup / "assets" if backup is not None else None
    if backup is not None:
        try:
            directory = _open_directory(backup, create=True, private=True)
            _close_directory(directory)
        except (OSError, UnsafeAssetError) as error:
            raise RuntimeError("Could not prepare the asset backup.") from error
    summary = {key: 0 for key in (
        "transcripts", "missing_transcript_ids", "unreadable_transcripts", "embedded_images", "invalid_images",
        "local_files", "local_images", "missing_files", "missing_images", "remote_links",
        "unsafe_files", "unreadable_files", "backed_up_files", "artifact_references",
        "missing_output_files", "missing_linked_images", "missing_reference_links",
        "unverified_reference_links", "failed_file_sends", "unconfirmed_file_sends", "prepared_output_files",
    )}
    summary["diagnostic_version"] = 2
    entries = {}
    artifact_urls = set()
    failed_sends, unconfirmed_sends = set(), set()

    def add(key, entry, transcript=None, source=None, *, scope=None, context=None):
        existing = entries.setdefault(key, entry)
        if transcript is not None:
            existing.setdefault("transcripts", set()).add(str(transcript))
        if source is not None:
            existing.setdefault("sources", set()).add(source)
        if scope is not None:
            existing.setdefault("scopes", set()).add(scope)
        if context is not None:
            existing.setdefault("contexts", set()).add(context)
        return existing

    def reference(raw, cwd, transcript, source, *, image=False, artifact=False, context=None):
        scope = "output" if source != "markdown" else "linked_image" if image else "reference"

        def record(key, entry):
            return add(key, entry, transcript, source, scope=scope, context=context)

        if not isinstance(raw, str) or not raw.strip():
            record(("invalid_reference", source, str(transcript)),
                   {"kind": "image" if image else "file", "status": "unsafe", "reason": "invalid_reference"})
            return
        # Whitespace is part of a local path. Trimming it can turn an unsafe
        # Windows alias into a different, valid file before validation.
        if source == "markdown" and ("${" in raw or "{{" in raw or "}}" in raw or raw.startswith("$(")):
            return
        # A source-code citation is a path plus an editor location, not a URI.
        citation = None
        if source == "markdown" and not raw.lower().startswith(("http://", "https://")):
            match = re.fullmatch(r"(.+?):(\d+)(?::(\d+))?", raw)
            if match:
                raw = match.group(1)
                citation = {"line": int(match.group(2))}
                if match.group(3) is not None:
                    citation["column"] = int(match.group(3))
        windows_path = os.name == "nt" and bool(re.match(r"^[A-Za-z]:[\\/]", raw))
        # urlsplit strips leading ASCII whitespace and embedded tabs/newlines.
        # Only parse a URI when its scheme starts at the first character;
        # ordinary paths must reach filesystem validation without that rewrite.
        literal_path = windows_path or not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw)
        try:
            parsed = urlsplit("") if literal_path else urlsplit(raw)
        except ValueError:
            record(("invalid_reference", source, str(transcript)),
                   {"kind": "image" if image else "file", "status": "unsafe", "reason": "invalid_reference"})
            return
        if parsed.scheme in ("http", "https") and parsed.netloc:
            if artifact:
                artifact_urls.add(raw)
            record(("remote", raw), {"kind": "image" if image else "file", "status": "remote", "url": raw})
            return
        if windows_path:
            pass
        elif parsed.scheme == "file" and parsed.netloc in ("", "localhost"):
            raw = unquote(parsed.path)
            if os.name == "nt" and re.match(r"^/[A-Za-z]:/", raw):
                raw = raw[1:]
        elif parsed.scheme:
            record(("unsupported", raw), {"kind": "image" if image else "file", "status": "unsafe", "reason": "unsupported_scheme", "url": raw})
            return
        elif raw.startswith("#"):
            return
        elif source == "markdown":
            # Relative Markdown links have URL query/fragment semantics. Split
            # those delimiters without urlsplit's whitespace normalization.
            raw = unquote(re.split(r"[?#]", raw, maxsplit=1)[0])
        if source == "markdown" and not image and context and context.startswith("tool:") and raw.startswith(("/docs/", "/learn/")):
            record(("navigation", raw), {"kind": "link", "status": "navigation", "url": raw, "reason": "documentation_navigation"})
            return
        path = Path(raw)
        if source == "markdown" and not image and not (path.is_absolute() or raw.startswith(("./", "../")) or path.suffix):
            record(("navigation", raw), {"kind": "link", "status": "navigation", "url": raw, "reason": "relative_navigation"})
            return
        if not path.is_absolute():
            if not isinstance(cwd, str) or not Path(cwd).is_absolute():
                record(("relative_without_cwd", raw), {"kind": "image" if image else "file", "status": "unsafe", "reason": "relative_path_without_cwd"})
                return
            path = Path(cwd) / path
        image = image or path.suffix.lower() in _IMAGE_SUFFIXES
        try:
            path = _absolute(path)
        except UnsafeAssetError as error:
            record(("unsafe_file", str(path)),
                   {"kind": "image" if image else "file", "status": "unsafe",
                    "path": str(path), "reason": str(error)})
            return
        if source == "markdown" and image and citation is None:
            scope = "linked_image"
        key = ("file", str(path))
        if key not in entries:
            entry = {"kind": "image" if image else "file", "status": "available", "path": str(path)}
            try:
                entry.update(_capture(path, assets))
            except FileNotFoundError:
                entry.update(status="missing", reason="file_not_found")
            except UnsafeAssetError as error:
                entry.update(status="unsafe", reason=str(error))
            except OSError:
                entry.update(status="unreadable", reason="file_unreadable")
        else:
            entry = entries[key]
            if image:
                entry["kind"] = "image"
        record(key, entry)
        if citation:
            entry.setdefault("citations", set()).add((citation["line"], citation.get("column")))

    def markdown(text, cwd, transcript, *, generated=False, context="assistant"):
        if not isinstance(text, str):
            return
        for match in _MARKDOWN_LINK.finditer(text):
            reference(match.group(2) or match.group(3), cwd, transcript, "markdown", image=bool(match.group(1)), context=context)
        if generated:
            for match in _GENERATED_PATH.finditer(text):
                reference(match.group(1), cwd, transcript, "generated_image", image=True, context=context)
            try:
                payload = json.loads(text)
            except (ValueError, TypeError):
                return
            if isinstance(payload, dict):
                for key in ("path", "image_path", "output_path", "file_path", "image_url"):
                    if isinstance(payload.get(key), str):
                        reference(payload[key], cwd, transcript, "generated_image", image=True, context=context)

    def image_block(block, transcript):
        source, file = block.get("source"), block.get("file")
        if isinstance(source, dict) and source.get("type") == "url":
            reference(source.get("url"), None, transcript, "image_block", image=True)
            return
        if isinstance(source, dict) and source.get("type") == "base64":
            data, media_type = source.get("data"), source.get("media_type")
        elif isinstance(file, dict):
            data, media_type = file.get("base64"), file.get("type")
        else:
            data, media_type = None, None
        try:
            if not isinstance(media_type, str) or not media_type.startswith("image/") or not isinstance(data, str) or not data:
                raise ValueError
            decoded = base64.b64decode(data, validate=True)
            if not decoded or not _image_signature_matches(decoded, media_type):
                raise ValueError
        except (ValueError, binascii.Error):
            fingerprint = hashlib.sha256(json.dumps(block, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
            add(("invalid_image", fingerprint), {"kind": "image", "status": "invalid", "reason": "invalid_embedded_image", "sha256": fingerprint}, transcript, "image_block", scope="output")
            return
        digest = hashlib.sha256(decoded).hexdigest()
        add(("embedded", digest), {"kind": "image", "status": "embedded", "sha256": digest, "bytes": len(decoded), "media_type": media_type}, transcript, "image_block", scope="output")

    def published(value, cwd, transcript):
        if not isinstance(value, list):
            return
        for item in value:
            if not isinstance(item, dict):
                continue
            if "sourcePath" in item:
                reference(item["sourcePath"], cwd, transcript, "published_artifact", context="published_artifact")
            for key in ("url", "artifactUrl"):
                if isinstance(item.get(key), str):
                    reference(item[key], cwd, transcript, "published_artifact", artifact=True, context="published_artifact")

    registered = {}
    for record in records:
        cwd = record.get("cwd")
        published(record.get("publishedArtifacts"), cwd, None)
        prior = record.get("priorCliSessionIds", [])
        ids = [record.get("cliSessionId"), *(prior if isinstance(prior, list) else [])]
        for sid in ids:
            if _is_uuid(sid):
                registered.setdefault(sid, cwd)
    index = {}
    for path in sorted(projects.glob("*/*.jsonl")):
        if path.stem in registered:
            index.setdefault(path.stem, []).append(path)

    for sid, fallback_cwd in sorted(registered.items()):
        paths = index.get(sid, [])
        if not paths:
            add(("transcript", sid), {"kind": "transcript", "status": "missing", "reason": "transcript_not_found", "session_id": sid})
            continue
        for path in paths:
            summary["transcripts"] += 1
            tools, pending_sends, completed_sends = {}, {}, set()

            def send_attempt(tool_id, details, status):
                key = (str(path), tool_id)
                (failed_sends if status == "send_failed" else unconfirmed_sends).add(key)
                for position, raw in enumerate(details["files"]):
                    entry = {"kind": "file", "status": status, "reason": "tool_result_error" if status == "send_failed" else "tool_result_not_found", "tool_use_id": tool_id}
                    if isinstance(raw, str):
                        try:
                            target = Path(raw) if Path(raw).is_absolute() else Path(details["cwd"]) / raw
                            entry["path"] = str(_absolute(target))
                        except (TypeError, ValueError):
                            pass
                    add(("send_attempt", *key, position), entry, path, "user_file", scope="attempt", context="tool:SendUserFile")

            def walk(value, cwd, *, text_allowed=False, generated=False, context="assistant"):
                if isinstance(value, dict):
                    published(value.get("publishedArtifacts"), cwd, path)
                    kind = value.get("type")
                    if kind == "image":
                        image_block(value, path)
                        return
                    if kind == "tool_use":
                        name = str(value.get("name", ""))
                        tool_id = value.get("id")
                        tools[tool_id] = name
                        tool_input = value.get("input")
                        if name.rsplit("__", 1)[-1] == "SendUserFile" and isinstance(tool_input, dict) and isinstance(tool_input.get("files"), list):
                            pending_sends[tool_id] = {"files": tool_input["files"], "cwd": cwd}
                        return
                    if kind == "tool_result":
                        tool_id = value.get("tool_use_id")
                        name = tools.get(tool_id, "unknown")
                        text_allowed = True
                        generated = bool(_GENERATED_TOOL.search(name)) and not value.get("is_error")
                        context = "tool:" + name
                        if tool_id in pending_sends and tool_id not in completed_sends:
                            details = pending_sends[tool_id]
                            if value.get("is_error"):
                                send_attempt(tool_id, details, "send_failed")
                            else:
                                for raw in details["files"]:
                                    reference(raw, details["cwd"], path, "user_file", context="tool:SendUserFile")
                            completed_sends.add(tool_id)
                    if kind == "text" and text_allowed:
                        markdown(value.get("text"), cwd, path, generated=generated, context=context)
                    for key, item in value.items():
                        if key in ("publishedArtifacts", "input"):
                            continue
                        if isinstance(item, str) and text_allowed and key == "content":
                            markdown(item, cwd, path, generated=generated, context=context)
                        elif isinstance(item, (dict, list)):
                            walk(item, cwd, text_allowed=text_allowed, generated=generated, context=context)
                elif isinstance(value, list):
                    for item in value:
                        walk(item, cwd, text_allowed=text_allowed, generated=generated, context=context)

            try:
                with _regular_stream(path) as stream:
                    before = _identity(os.fstat(stream.fileno()))
                    for line in stream:
                        if not line.strip():
                            continue
                        entry = json.loads(line)
                        if not isinstance(entry, dict):
                            raise ValueError
                        cwd = entry.get("cwd", fallback_cwd)
                        message = entry.get("message", {})
                        assistant = entry.get("type") == "assistant" or isinstance(message, dict) and message.get("role") == "assistant"
                        if assistant and isinstance(message, dict) and isinstance(message.get("content"), str):
                            markdown(message["content"], cwd, path)
                        walk(entry, cwd, text_allowed=assistant)
                    if before != _identity(os.fstat(stream.fileno())):
                        raise RuntimeError("Transcript changed during the asset audit.")
            except (OSError, ValueError, UnsafeAssetError):
                add(("transcript", str(path)), {"kind": "transcript", "status": "unreadable", "path": str(path), "reason": "transcript_unreadable"})
            for tool_id, details in pending_sends.items():
                if tool_id not in completed_sends:
                    send_attempt(tool_id, details, "send_unconfirmed")

    for entry in entries.values():
        status = entry["status"]
        scopes = entry.get("scopes", set())
        entry["scope"] = "output" if "output" in scopes else "linked_image" if "linked_image" in scopes else "attempt" if "attempt" in scopes else "reference"
        output = entry["scope"] == "output"
        if entry["kind"] == "transcript":
            summary["missing_transcript_ids" if status == "missing" else "unreadable_transcripts"] += 1
        elif status == "embedded":
            summary["embedded_images"] += 1
        elif status == "invalid":
            summary["invalid_images"] += 1
        elif status == "remote":
            summary["remote_links"] += 1
        elif status == "available":
            summary["local_files"] += 1
            summary["local_images"] += entry["kind"] == "image"
            summary["backed_up_files"] += "backup_path" in entry
            if output and backup is not None:
                entry["output_path"] = _prepare_output(entry, backup / "output-files")
                summary["prepared_output_files"] += 1
        elif status == "missing":
            summary["missing_files"] += 1
            summary["missing_images"] += entry["kind"] == "image"
            summary["missing_output_files" if output else "missing_linked_images" if entry["scope"] == "linked_image" else "missing_reference_links"] += 1
        elif status == "unsafe":
            summary["unsafe_files" if output else "unverified_reference_links"] += 1
        elif status == "unreadable":
            summary["unreadable_files" if output else "unverified_reference_links"] += 1
        for key in ("transcripts", "sources", "scopes", "contexts"):
            if key in entry:
                entry[key] = sorted(entry[key])
        if "citations" in entry:
            entry["citations"] = [{"line": line, **({"column": column} if column is not None else {})} for line, column in sorted(entry["citations"], key=lambda item: (item[0], item[1] or 0))]
    summary["artifact_references"] = len(artifact_urls)
    summary["failed_file_sends"] = len(failed_sends)
    summary["unconfirmed_file_sends"] = len(unconfirmed_sends)
    return {"version": 1, "diagnostic_version": 2, "summary": summary, "entries": list(entries.values())}
