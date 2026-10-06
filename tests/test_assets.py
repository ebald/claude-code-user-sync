"""Asset evidence and snapshots use synthetic local data only."""
from __future__ import annotations

import base64
import copy
import errno
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import uuid

import asset_audit
from tests.support import assert_private_mode, create_symlink

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9i8AAAAASUVORK5CYII=")
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


class AssetAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-assets-tests-")
        self.addCleanup(self.temp.cleanup)
        # macOS exposes its temporary root through a system /var symlink.
        self.base = Path(self.temp.name).resolve()
        self.projects = self.base / "projects"
        (self.projects / "project").mkdir(parents=True)
        self.cwd = self.base / "work"
        self.cwd.mkdir()
        self.sid = str(uuid.uuid4())
        self.record = {"cliSessionId": self.sid, "cwd": str(self.cwd)}
        self.transcript = self.projects / "project" / (self.sid + ".jsonl")

    def write_transcript(self, content, *, sid=None, kind="assistant", confirm_sends=True):
        sid = sid or self.sid
        path = self.projects / "project" / (sid + ".jsonl")
        lines = [json.dumps({
            "type": kind, "sessionId": sid, "cwd": str(self.cwd),
            "message": {"role": kind, "content": content},
        })]
        if confirm_sends and isinstance(content, list):
            results = [{"type": "tool_result", "tool_use_id": item.get("id"), "content": "Synthetic successful send"}
                       for item in content if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "SendUserFile"]
            if results:
                lines.append(json.dumps({"type": "user", "sessionId": sid, "cwd": str(self.cwd), "message": {"role": "user", "content": results}}))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def audit(self, **kwargs):
        return asset_audit.audit_assets([self.record], self.projects, **kwargs)

    def test_both_embedded_image_schemas_validate_and_deduplicate_payload(self):
        payload = base64.b64encode(PNG).decode()
        second = base64.b64encode(GIF).decode()
        self.write_transcript([
            {"type": "image", "source": {"type": "base64", "data": payload, "media_type": "image/png"}},
            {"type": "image", "file": {"base64": payload, "type": "image/png", "originalSize": 19, "dimensions": {"width": 1, "height": 1}}},
            {"type": "image", "file": {"base64": second, "type": "image/gif"}},
        ], kind="user")
        before = self.transcript.read_bytes()
        report = self.audit()
        self.assertEqual(report["summary"]["embedded_images"], 2)
        self.assertEqual(report["summary"]["invalid_images"], 0)
        manifest = json.dumps(report)
        self.assertNotIn(payload, manifest)
        self.assertNotIn(second, manifest)
        self.assertNotIn("synthetic image", manifest)
        self.assertEqual(self.transcript.read_bytes(), before)

    def test_present_missing_artifact_user_file_and_markdown_references(self):
        file = self.cwd / "report.txt"
        file.write_bytes(b"synthetic document")
        image = self.cwd / "generated image.png"
        image.write_bytes(b"synthetic image")
        self.record["publishedArtifacts"] = [
            {"sourcePath": "report.txt", "url": "https://example.test/artifact/one"},
            {"sourcePath": "absent.html", "url": "https://example.test/artifact/one"},
        ]
        self.write_transcript([
            {"type": "tool_use", "id": "send-one", "name": "SendUserFile", "input": {"files": [str(file), str(image), "missing.png"]}},
            {"type": "text", "text": f"[Report]({file}) ![Image](<{image}>) ![Absent](missing.png)"},
        ])
        before = {p: p.read_bytes() for p in (file, image, self.transcript)}
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["local_files"], 2)
        self.assertEqual(report["summary"]["local_images"], 1)
        self.assertEqual(report["summary"]["missing_files"], 2)
        self.assertEqual(report["summary"]["missing_output_files"], 2)
        self.assertEqual(report["summary"]["missing_linked_images"], 0)
        self.assertEqual(report["summary"]["missing_images"], 1)
        self.assertEqual(report["summary"]["backed_up_files"], 2)
        self.assertEqual(report["summary"]["artifact_references"], 1)
        self.assertEqual(report["summary"]["remote_links"], 1)
        available = [entry for entry in report["entries"] if entry["status"] == "available"]
        for entry in available:
            original = before[Path(entry["path"])]
            snapshot = Path(entry["backup_path"])
            self.assertEqual(entry["sha256"], hashlib.sha256(original).hexdigest())
            self.assertEqual(snapshot.read_bytes(), original)
            self.assertEqual(snapshot.name, entry["sha256"])
            assert_private_mode(self, snapshot, 0o600)
            assert_private_mode(self, snapshot.parent, 0o700)
            output = Path(entry["output_path"])
            self.assertEqual(output.name, Path(entry["path"]).name)
            self.assertEqual(output.suffix, Path(entry["path"]).suffix)
            self.assertEqual(output.read_bytes(), original)
            assert_private_mode(self, output, 0o600)
            assert_private_mode(self, output.parent, 0o700)
            self.assertNotEqual(snapshot.stat().st_ino, output.stat().st_ino)
        self.assertIn("published_artifact", next(e for e in available if e["path"] == str(file))["sources"])
        for path, original in before.items():
            self.assertEqual(path.read_bytes(), original)

    def test_duplicate_records_and_all_registered_prior_transcripts_scan_once(self):
        previous = str(uuid.uuid4())
        self.record["priorCliSessionIds"] = [previous, previous]
        payload = base64.b64encode(PNG).decode()
        content = [{"type": "image", "source": {"type": "base64", "data": payload, "media_type": "image/png"}}]
        self.write_transcript(content)
        self.write_transcript(content, sid=previous)
        unused = str(uuid.uuid4())
        self.write_transcript([{ "type": "image", "file": {"base64": "!", "type": "image/png"}}], sid=unused)
        report = asset_audit.audit_assets([self.record, dict(self.record)], self.projects)
        self.assertEqual(report["summary"]["transcripts"], 2)
        self.assertEqual(report["summary"]["embedded_images"], 1)
        self.assertEqual(report["summary"]["invalid_images"], 0)
        self.assertEqual(len(report["entries"][0]["transcripts"]), 2)

    def test_symlinks_and_nonregular_files_are_refused_without_copying(self):
        outside = self.base / "outside.png"
        outside.write_bytes(b"do not copy me")
        link = self.cwd / "link.png"
        create_symlink(self, link, outside)
        linked_dir = self.cwd / "linked-directory"
        create_symlink(self, linked_dir, self.base, directory=True)
        directory = self.cwd / "directory.png"
        directory.mkdir()
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(link), str(linked_dir / outside.name), str(directory)]}}])
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["unsafe_files"], 3)
        self.assertEqual(report["summary"]["backed_up_files"], 0)
        self.assertFalse((self.base / "backup/assets").exists())
        self.assertEqual(outside.read_bytes(), b"do not copy me")
        with self.assertRaises(asset_audit.UnsafeAssetError):
            asset_audit.safe_asset_hash(link)

    def test_strict_base64_empty_or_wrong_media_type_is_invalid(self):
        good = base64.b64encode(b"image").decode()
        invalid = {"type": "image", "source": {"type": "base64", "data": "not!base64", "media_type": "image/png"}}
        self.write_transcript([
            invalid, invalid,
            {"type": "image", "file": {"base64": "", "type": "image/png"}},
            {"type": "image", "file": {"base64": good, "type": "text/plain"}},
            {"type": "image", "source": {"type": "base64", "data": good + "\n", "media_type": "image/png"}},
        ])
        report = self.audit()
        self.assertEqual(report["summary"]["invalid_images"], 4)
        self.assertEqual(report["summary"]["embedded_images"], 0)
        self.assertNotIn("not!base64", json.dumps(report))

    def test_remote_links_and_tool_result_image_links_are_recorded_without_fetching(self):
        image = self.cwd / "generated.png"
        image.write_bytes(b"image generated by synthetic tool")
        self.write_transcript([
            {"type": "tool_use", "name": "mcp__test__generate_image", "id": "imagegen", "input": {}},
            {"type": "tool_result", "tool_use_id": "imagegen", "content": [{"type": "text", "text": f"Created `{image}`"}]},
            {"type": "tool_result", "tool_use_id": "another-tool", "content": f"![Generated]({image}) ![Remote](https://example.test/image.png)"},
            {"type": "image", "source": {"type": "url", "url": "https://example.test/image.png"}},
        ], kind="user")
        report = self.audit()
        self.assertEqual(report["summary"]["local_images"], 1)
        self.assertEqual(report["summary"]["remote_links"], 1)
        self.assertEqual(report["summary"]["embedded_images"], 0)
        entry = next(e for e in report["entries"] if e["status"] == "available")
        self.assertEqual(entry["sources"], ["generated_image", "markdown"])

    def test_arbitrary_prose_user_links_and_tool_input_paths_are_not_assets(self):
        self.write_transcript([
            {"type": "text", "text": "Edit /some/project/app.py and `./file.png` soon."},
            {"type": "tool_use", "name": "Write", "id": "write", "input": {"file_path": "/some/project/other.py"}},
        ])
        self.transcript.write_text(self.transcript.read_text() + json.dumps({"type": "user", "message": {"role": "user", "content": "[mentioned](uncreated.csv)"}}) + "\n")
        self.assertEqual(self.audit()["entries"], [])

    def test_unreadable_missing_and_malformed_transcripts_are_visible(self):
        self.record["priorCliSessionIds"] = [str(uuid.uuid4())]
        self.transcript.write_text("not json\n")
        report = self.audit()
        self.assertEqual(report["summary"]["transcripts"], 1)
        self.assertEqual(report["summary"]["unreadable_transcripts"], 1)
        self.assertEqual(report["summary"]["missing_transcript_ids"], 1)
        self.assertNotIn("not json", json.dumps(report))

    def test_failed_relative_send_retried_successfully_does_not_become_missing_output(self):
        document = self.cwd / "report.txt"
        document.write_bytes(b"Synthetic successful retry")
        self.write_transcript([
            {"type": "tool_use", "id": "failed", "name": "SendUserFile", "input": {"files": ["wrong-directory/report.txt"]}},
            {"type": "tool_result", "tool_use_id": "failed", "is_error": True, "content": "Synthetic send failure"},
            {"type": "tool_use", "id": "success", "name": "SendUserFile", "input": {"files": [str(document)]}},
            {"type": "tool_result", "tool_use_id": "success", "content": "Synthetic completed send"},
        ], confirm_sends=False)
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["diagnostic_version"], 2)
        self.assertEqual(report["summary"]["failed_file_sends"], 1)
        self.assertEqual(report["summary"]["missing_files"], 0)
        self.assertEqual(report["summary"]["missing_output_files"], 0)
        self.assertEqual(report["summary"]["prepared_output_files"], 1)
        failed = next(e for e in report["entries"] if e["status"] == "send_failed")
        self.assertEqual(failed["scope"], "attempt")
        self.assertNotIn("sha256", failed)

    def test_unconfirmed_send_has_evidence_without_asserting_file_missing(self):
        self.write_transcript([{"type": "tool_use", "id": "pending", "name": "SendUserFile", "input": {"files": ["not-created-yet.png"]}}], confirm_sends=False)
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["unconfirmed_file_sends"], 1)
        self.assertEqual(report["summary"]["missing_files"], 0)
        self.assertEqual(report["entries"][0]["status"], "send_unconfirmed")
        self.assertFalse((self.base / "backup/assets").exists())

    def test_tool_documentation_routes_remain_navigation_evidence(self):
        self.write_transcript([
            {"type": "tool_use", "id": "web", "name": "WebFetch", "input": {}},
            {"type": "tool_result", "tool_use_id": "web", "content": "[Docs](/docs/app/getting-started) [Learn](/learn/react-foundations)"},
        ], kind="user")
        report = self.audit()
        self.assertEqual(report["summary"]["missing_files"], 0)
        self.assertEqual(report["summary"]["missing_reference_links"], 0)
        self.assertEqual(len(report["entries"]), 2)
        self.assertEqual({e["status"] for e in report["entries"]}, {"navigation"})
        self.assertEqual({tuple(e["contexts"]) for e in report["entries"]}, {("tool:WebFetch",)})

    def test_code_citations_normalize_before_url_parse_and_retain_location(self):
        code = self.cwd / "mockup-v2.html"
        code.write_bytes(b"<html>Synthetic source</html>")
        self.write_transcript([{"type": "text", "text": f"[Source](mockup-v2.html:12) [Second]({code}:34:5)"}])
        report = self.audit()
        self.assertEqual(report["summary"]["missing_files"], 0)
        self.assertEqual(report["summary"]["unsafe_files"], 0)
        self.assertEqual(report["summary"]["local_files"], 1)
        self.assertEqual(report["entries"][0]["path"], str(code))
        self.assertEqual(report["entries"][0]["scope"], "reference")
        self.assertEqual(report["entries"][0]["citations"], [{"line": 12}, {"line": 34, "column": 5}])

    def test_templates_are_not_files_but_missing_artifact_image_and_reference_stay_visible(self):
        self.record["publishedArtifacts"] = [{"sourcePath": "missing-output.html"}]
        self.write_transcript([{"type": "text", "text": "[Template](${file.url}) [Second](${data.instagram}) ![Image](missing-image.png) [Source](missing-source.ts:14)"}])
        report = self.audit()
        self.assertEqual(report["summary"]["missing_output_files"], 1)
        self.assertEqual(report["summary"]["missing_linked_images"], 1)
        self.assertEqual(report["summary"]["missing_reference_links"], 1)
        self.assertEqual(report["summary"]["missing_files"], 3)
        self.assertNotIn("${", json.dumps(report))

    def test_generic_markdown_symlinks_and_directories_are_informational(self):
        real = self.cwd / "real.txt"
        real.write_bytes(b"source file")
        link = self.cwd / "link.txt"
        create_symlink(self, link, real)
        directory = self.cwd / "directory"
        directory.mkdir()
        self.write_transcript([{"type": "text", "text": f"[Linked]({link}) [Directory]({directory})"}])
        report = self.audit()
        self.assertEqual(report["summary"]["unsafe_files"], 0)
        self.assertEqual(report["summary"]["unverified_reference_links"], 2)
        self.assertEqual({e["status"] for e in report["entries"]}, {"unsafe"})

    def published_output_fixture(self, name="published.html"):
        source = self.cwd / name
        source.write_bytes(b"<html>Synthetic published version</html>")
        self.record["publishedArtifacts"] = [{"sourcePath": str(source)}]
        self.write_transcript([])
        previous = self.audit(backup_dir=self.base / "old-backup")
        source.unlink()
        current = self.audit()
        return source, previous, current

    def test_exact_path_recovery_prepares_verified_copy_without_restoring_original(self):
        source, previous, current = self.published_output_fixture()
        before = copy.deepcopy(previous)
        result = asset_audit.recover_preserved_outputs(current, [previous], self.base / "recovery")
        entry = next(e for e in result["entries"] if e.get("path") == str(source))
        self.assertIs(result, current)
        self.assertEqual(previous, before)
        self.assertFalse(source.exists())
        self.assertEqual(entry["status"], "missing")
        self.assertTrue(entry["preserved_from_backup"])
        self.assertEqual(entry["recovery_kind"], "previous_backup")
        self.assertEqual(Path(entry["output_path"]).suffix, ".html")
        self.assertEqual(Path(entry["output_path"]).read_bytes(), b"<html>Synthetic published version</html>")
        self.assertEqual(asset_audit.safe_asset_hash(Path(entry["backup_path"])), entry["sha256"])
        self.assertEqual(result["summary"]["missing_output_files"], 1)
        self.assertEqual(result["summary"]["preserved_output_files"], 1)
        self.assertEqual(result["summary"]["unpreserved_output_files"], 0)
        self.assertEqual(result["summary"]["prepared_output_files"], 1)
        assert_private_mode(self, Path(entry["output_path"]), 0o600)

    def test_recovery_does_not_guess_matching_basename_in_other_directory(self):
        source, previous, _ = self.published_output_fixture()
        different = self.cwd / "other-directory" / source.name
        self.record["publishedArtifacts"] = [{"sourcePath": str(different)}]
        current = self.audit()
        asset_audit.recover_preserved_outputs(current, [previous], self.base / "recovery")
        entry = next(e for e in current["entries"] if e.get("path") == str(different))
        self.assertNotIn("preserved_from_backup", entry)
        self.assertFalse(different.exists())
        self.assertEqual(current["summary"]["preserved_output_files"], 0)
        self.assertEqual(current["summary"]["unpreserved_output_files"], 1)
        self.assertEqual(current["recovery_unavailable"], [{"path": str(different), "reason": "no_previous_backup"}])

    def test_recovery_known_hash_corruption_aborts_without_asserting_success(self):
        source, previous, current = self.published_output_fixture()
        prior_entry = next(e for e in previous["entries"] if e.get("path") == str(source))
        Path(prior_entry["backup_path"]).write_bytes(b"Corrupted older snapshot")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            asset_audit.recover_preserved_outputs(current, [previous], self.base / "recovery")
        self.assertFalse(source.exists())
        current_entry = next(e for e in current["entries"] if e.get("path") == str(source))
        self.assertNotIn("preserved_from_backup", current_entry)
        self.assertFalse((self.base / "recovery/output-files").exists())
        self.assertEqual(list((self.base / "recovery/assets").iterdir()), [])

    def test_preserved_missing_output_survives_and_can_be_reused_in_later_sync(self):
        source, previous, current = self.published_output_fixture()
        asset_audit.recover_preserved_outputs(current, [previous], self.base / "second")
        old_entry = next(e for e in previous["entries"] if e.get("path") == str(source))
        Path(old_entry["backup_path"]).unlink()
        third = self.audit()
        asset_audit.recover_preserved_outputs(third, [current, previous], self.base / "third")
        entry = next(e for e in third["entries"] if e.get("path") == str(source))
        self.assertTrue(entry["preserved_from_backup"])
        self.assertEqual(entry["status"], "missing")
        self.assertFalse(source.exists())
        self.assertEqual(Path(entry["output_path"]).read_bytes(), b"<html>Synthetic published version</html>")
        self.assertEqual(third["summary"]["preserved_output_files"], 1)
        # Re-running the same operation verifies its cache without double counts.
        asset_audit.recover_preserved_outputs(third, [current], self.base / "third")
        self.assertEqual(third["summary"]["prepared_output_files"], 1)

    def test_missing_newest_backup_is_reported_and_older_exact_snapshot_can_recover(self):
        source, previous, current = self.published_output_fixture()
        newest = copy.deepcopy(previous)
        prior_entry = next(e for e in newest["entries"] if e.get("path") == str(source))
        prior_entry["status"] = "cached"
        prior_entry["backup_path"] = str(self.base / "absent-snapshot")
        asset_audit.recover_preserved_outputs(current, [newest, previous], self.base / "recovery")
        self.assertEqual(current["summary"]["preserved_output_files"], 1)
        self.assertEqual(current["recovery_unavailable"], [{"path": str(source), "backup_path": str(self.base / "absent-snapshot"), "reason": "previous_backup_not_found"}])

    def test_source_change_is_detected_or_prevented_during_snapshot(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"original synthetic report")
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(source)]}}])
        original_stream = asset_audit._stream_hash

        def change_after_read(stream, output=None):
            digest = original_stream(stream, output)
            if os.name == "nt":
                with self.assertRaises(OSError):
                    source.write_bytes(b"modified during snapshot")
            else:
                source.write_bytes(b"modified during snapshot")
            return digest

        with mock.patch.object(asset_audit, "_stream_hash", side_effect=change_after_read):
            if os.name == "nt":
                report = self.audit(backup_dir=self.base / "backup")
                entry = next(e for e in report["entries"] if e["status"] == "available")
                self.assertEqual(Path(entry["backup_path"]).read_bytes(), b"original synthetic report")
                self.assertEqual(source.read_bytes(), b"original synthetic report")
            else:
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    self.audit(backup_dir=self.base / "backup")
                self.assertEqual(list((self.base / "backup/assets").iterdir()), [])

    def test_backup_write_failure_aborts_and_removes_partial_copy(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"original synthetic report")
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(source)]}}])
        before = self.transcript.read_bytes()

        def disk_full(stream, output=None):
            output.write(b"partial")
            raise OSError(errno.ENOSPC, "Synthetic disk full")

        with mock.patch.object(asset_audit, "_stream_hash", side_effect=disk_full):
            with self.assertRaisesRegex(RuntimeError, "asset backup"):
                self.audit(backup_dir=self.base / "backup")
        self.assertEqual(source.read_bytes(), b"original synthetic report")
        self.assertEqual(self.transcript.read_bytes(), before)
        self.assertEqual(list((self.base / "backup/assets").iterdir()), [])

    def test_existing_corrupt_or_symlink_snapshot_aborts(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"original synthetic report")
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(source)]}}])
        assets = self.base / "backup/assets"
        assets.mkdir(parents=True)
        target = assets / hashlib.sha256(source.read_bytes()).hexdigest()
        target.write_bytes(b"corrupt content")
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            self.audit(backup_dir=assets.parent)
        target.unlink()
        create_symlink(self, target, source)
        with self.assertRaisesRegex(RuntimeError, "asset backup"):
            self.audit(backup_dir=assets.parent)
        self.assertEqual(source.read_bytes(), b"original synthetic report")

    def test_content_addressed_backup_is_shared_for_distinct_identical_files(self):
        first = self.cwd / "one.txt"
        second = self.cwd / "two.txt"
        first.write_bytes(b"identical payload")
        second.write_bytes(first.read_bytes())
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(first), str(second), str(first)]}}])
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["local_files"], 2)
        self.assertEqual(len(list((self.base / "backup/assets").iterdir())), 1)
        self.assertEqual(len({e["backup_path"] for e in report["entries"]}), 1)
        self.assertEqual(asset_audit.safe_asset_hash(first), hashlib.sha256(b"identical payload").hexdigest())

    def test_valid_base64_with_wrong_image_signature_is_invalid(self):
        self.write_transcript([
            {"type": "image", "source": {"type": "base64", "data": base64.b64encode(b"not an image").decode(), "media_type": "image/png"}},
            {"type": "image", "file": {"base64": base64.b64encode(GIF).decode(), "type": "image/jpeg"}},
        ])
        self.assertEqual(self.audit()["summary"]["invalid_images"], 2)

    def test_windows_lexical_aliases_are_rejected_before_path_normalization(self):
        unsafe = [r"C:\work\ambiguous. ", r"C:\work\ambiguous.",
                  r"C:\work\NUL.txt", r"C:\work\file.txt:hidden", r"C:relative",
                  "C:\\work\\COM\u00b9.txt", "C:\\work\\invalid\x00.txt",
                  r"\\server\share\file.txt", r"\\?\C:\work\file.txt"]
        for path in unsafe:
            with self.subTest(path=path):
                with self.assertRaises(asset_audit.UnsafeAssetError):
                    asset_audit._validate_windows_components(PureWindowsPath(path))
        asset_audit._validate_windows_components(PureWindowsPath(r"C:\ordinary folder\file.txt"))
        asset_audit._validate_windows_components(PureWindowsPath(r"..\images\file.png"))

    def test_reparse_metadata_is_rejected_even_when_not_a_symbolic_link(self):
        info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0x400)
        with mock.patch.object(Path, "lstat", return_value=info):
            self.assertTrue(asset_audit.is_link(self.cwd))
            with self.assertRaises(asset_audit.UnsafeAssetError):
                asset_audit.assert_no_links(self.cwd / "output.png")

    @unittest.skipUnless(os.name == "nt", "Windows native file handles required")
    def test_windows_file_uri_and_native_drive_paths_refer_to_the_same_asset(self):
        image = self.cwd / "native image.png"
        image.write_bytes(PNG)
        self.write_transcript([
            {"type": "text", "text": f"![Native](<{image}>) ![URI](<{image.as_uri()}>)"},
            {"type": "tool_use", "name": "generate_image", "id": "image", "input": {}},
            {"type": "tool_result", "tool_use_id": "image", "content": f"Created `{image}`"},
        ])
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["local_files"], 1)
        self.assertEqual(report["summary"]["prepared_output_files"], 1)
        entry = next(e for e in report["entries"] if e["status"] == "available")
        self.assertEqual(entry["path"], str(image))
        self.assertEqual(entry["sources"], ["generated_image", "markdown"])
        self.assertEqual(Path(entry["output_path"]).read_bytes(), PNG)

    @unittest.skipUnless(os.name == "nt", "Windows native file handles required")
    def test_windows_ancestor_cannot_be_replaced_during_asset_read(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"Synthetic stable file")
        original_stream = asset_audit._stream_hash

        def attempt_parent_replacement(stream, output=None):
            with self.assertRaises(OSError):
                self.cwd.rename(self.base / "moved-work")
            return original_stream(stream, output)

        with mock.patch.object(asset_audit, "_stream_hash", side_effect=attempt_parent_replacement):
            digest = asset_audit.safe_asset_hash(source)
        self.assertEqual(digest, hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse((self.base / "moved-work").exists())

    @unittest.skipUnless(os.name == "nt", "Windows native file handles required")
    def test_windows_junction_is_rejected_without_copying_its_target(self):
        target = self.base / "junction-target"
        target.mkdir()
        source = target / "report.txt"
        source.write_bytes(b"Synthetic junction target")
        junction = self.cwd / "junction"
        subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(junction), str(target)],
                       check=True, capture_output=True, text=True)
        self.addCleanup(lambda: junction.rmdir() if junction.exists() else None)
        self.assertTrue(asset_audit.is_link(junction))
        with self.assertRaises(asset_audit.UnsafeAssetError):
            asset_audit.safe_asset_hash(junction / source.name)
        self.assertFalse((self.base / "backup").exists())
        self.assertEqual(source.read_bytes(), b"Synthetic junction target")

    @unittest.skipUnless(os.name == "nt", "Windows lexical path semantics required")
    def test_windows_unsafe_reference_is_reported_without_aborting_the_audit(self):
        path = self.cwd / "ambiguous. "
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send",
                                "input": {"files": [str(path)]}}])
        report = self.audit(backup_dir=self.base / "backup")
        self.assertEqual(report["summary"]["unsafe_files"], 1)
        self.assertEqual(report["summary"]["backed_up_files"], 0)
        entry = next(e for e in report["entries"] if e["status"] == "unsafe")
        self.assertEqual(entry["path"], str(path))
        self.assertEqual(entry["reason"], "unsupported_windows_path")

    @unittest.skipUnless(os.name == "nt", "Windows native file handles required")
    def test_windows_devices_shares_and_alternate_data_streams_are_refused(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"Synthetic regular file")
        unsafe = [self.cwd / "NUL.txt", Path(str(source) + ":hidden"),
                  Path(r"\\server\share\report.txt"), self.cwd / "ambiguous. "]
        for path in unsafe:
            with self.subTest(path=path):
                with self.assertRaises(asset_audit.UnsafeAssetError):
                    asset_audit.safe_asset_hash(path)

    @unittest.skipUnless(Path("/var").is_symlink() and os.readlink("/var").lstrip("/") == "private/var", "macOS root alias required")
    def test_macos_system_var_alias_reads_real_source_and_still_refuses_attachment_links(self):
        source = self.cwd / "report.txt"
        source.write_bytes(b"macOS system alias fixture")
        if not str(source).startswith("/private/var/"):
            self.skipTest("temporary files are outside macOS /private/var")
        alias_source = Path(str(source).replace("/private/var/", "/var/", 1))
        self.assertEqual(asset_audit.safe_asset_hash(alias_source), hashlib.sha256(source.read_bytes()).hexdigest())
        link = self.cwd / "attachment-link.txt"
        create_symlink(self, link, source)
        alias_link = Path(str(link).replace("/private/var/", "/var/", 1))
        with self.assertRaises(asset_audit.UnsafeAssetError):
            asset_audit.safe_asset_hash(alias_link)
        alias_projects = Path(str(self.projects).replace("/private/var/", "/var/", 1))
        self.write_transcript([{"type": "tool_use", "name": "SendUserFile", "id": "send", "input": {"files": [str(alias_source)]}}])
        report = asset_audit.audit_assets([self.record], alias_projects)
        self.assertEqual(report["summary"]["local_files"], 1)
        self.assertEqual(report["summary"]["unreadable_transcripts"], 0)


if __name__ == "__main__":
    unittest.main()
