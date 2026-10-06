"""Safety checks against temporary, synthetic Claude Desktop data only."""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

import claude_sync
from tests.support import create_symlink


class SyncSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="claude-sync-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "catalogs"
        self.projects = self.base / "projects"
        self.projects.mkdir()
        self.a = self.root / "account-a" / "org-a"
        self.b = self.root / "account-b" / "org-b"
        self.a.mkdir(parents=True)
        self.b.mkdir(parents=True)
        self.backup = self.base / "backup"

    def record(self, **updates):
        session_id = "local_" + str(uuid.uuid4())
        cli_id = str(uuid.uuid4())
        result = {
            "sessionId": session_id,
            "cliSessionId": cli_id,
            "title": "Synthetic conversation",
            "cwd": str(self.base / "synthetic/project with spaces"),
            "originCwd": str(self.base / "synthetic/original project"),
            "createdAt": "2026-09-01T00:00:00Z",
            "lastActivityAt": "2026-09-02T00:00:00Z",
            "completedTurns": 1,
            "isArchived": False,
            "isStarred": False,
            "permissionMode": "default",
        }
        result.update(updates)
        return result

    def save_record(self, directory, record):
        path = directory / (record["sessionId"] + ".json")
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return path

    def transcript(self, record, cli_id=None):
        cli_id = cli_id or record["cliSessionId"]
        directory = self.projects / "-synthetic-project"
        directory.mkdir(exist_ok=True)
        path = directory / (cli_id + ".jsonl")
        lines = [
            {
                "type": "user",
                "sessionId": cli_id,
                "cwd": record["cwd"],
                "uuid": str(uuid.uuid4()),
                "message": {"role": "user", "content": "Synthetic test only"},
            },
            {
                "type": "assistant",
                "sessionId": cli_id,
                "uuid": str(uuid.uuid4()),
                "message": {"role": "assistant", "content": [{"type": "text", "text": "OK"}]},
            },
        ]
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        return path

    def plan(self):
        return claude_sync.build_plan(self.root, self.projects)

    def snapshot(self, directory=None):
        directory = directory or self.root
        return {
            str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }

    def catalog_changes(self, plan):
        return [
            change for change in plan["changes"]
            if Path(change["relative_path"]).name.startswith("local_")
            and change["relative_path"].endswith(".json")
        ]

    def test_bidirectional_copy_preserves_identity_and_project_paths(self):
        first = self.record(title="From account A")
        second = self.record(title="From account B")
        self.save_record(self.a, first)
        self.save_record(self.b, second)
        self.transcript(first)
        self.transcript(second)
        transcript_before = self.snapshot(self.projects)
        plan = self.plan()
        self.assertEqual(len(self.catalog_changes(plan)), 2)
        claude_sync.apply_plan(self.root, plan, self.backup)
        for directory, record in ((self.a, second), (self.b, first)):
            copied = json.loads((directory / (record["sessionId"] + ".json")).read_text())
            for key in ("sessionId", "cliSessionId", "cwd", "originCwd", "title"):
                self.assertEqual(copied[key], record[key])
        self.assertEqual(self.snapshot(self.projects), transcript_before)

    def test_runtime_auth_and_tool_permissions_are_not_copied(self):
        record = self.record(
            permissionMode="bypassPermissions",
            sessionSettings={"secret": "secret-session-settings"},
            remoteMcpServersConfig={"auth": "secret-server-auth"},
            enabledMcpTools=["dangerous-tool"],
            bridgeSessionIds=["secret-bridge-session"],
        )
        source = self.save_record(self.a, record)
        self.transcript(record)
        source_before = source.read_bytes()
        plan = self.plan()
        change = self.catalog_changes(plan)[0]
        copied = json.loads(base64.b64decode(change["data_b64"]))
        self.assertEqual(copied["permissionMode"], "default")
        for key in ("sessionSettings", "remoteMcpServersConfig", "enabledMcpTools", "bridgeSessionIds"):
            self.assertNotIn(key, copied)
        claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(source.read_bytes(), source_before)
        # The original and sanitized copy must compare as equivalent on the next run.
        again = self.plan()
        self.assertEqual(self.catalog_changes(again), [])
        self.assertEqual(again["conflicts"], [])

    def test_stale_transcript_unavailable_hint_does_not_block_or_conflict(self):
        record = self.record(transcriptUnavailable=True)
        self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        self.assertEqual(len(self.catalog_changes(plan)), 2)
        copied = json.loads(base64.b64decode(self.catalog_changes(plan)[0]["data_b64"]))
        self.assertNotIn("transcriptUnavailable", copied)
        claude_sync.apply_plan(self.root, plan, self.backup)
        original = json.loads((self.a / (record["sessionId"] + ".json")).read_bytes())
        self.assertNotIn("transcriptUnavailable", original)
        self.assertEqual(self.plan()["conflicts"], [])
        self.assertEqual(self.plan()["changes"], [])

    def test_missing_transcript_is_reported_and_not_copied(self):
        record = self.record()
        self.save_record(self.a, record)
        before = self.snapshot()
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["missing_transcripts"])
        self.assertEqual(self.snapshot(), before)

    def test_malformed_transcript_is_not_considered_restorable(self):
        record = self.record()
        self.save_record(self.a, record)
        path = self.transcript(record)
        path.write_text('{"type":"user"}\nnot json\n', encoding="utf-8")
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["missing_transcripts"])

    def test_empty_transcript_is_not_considered_restorable(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record).write_text("", encoding="utf-8")
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["missing_transcripts"])

    def test_transcript_for_a_different_session_is_not_considered_restorable(self):
        record = self.record()
        self.save_record(self.a, record)
        path = self.transcript(record)
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        wrong_id = str(uuid.uuid4())
        for line in lines:
            line["sessionId"] = wrong_id
        path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["missing_transcripts"])

    def test_prior_cli_session_id_can_locate_the_transcript(self):
        prior_id = str(uuid.uuid4())
        record = self.record(priorCliSessionIds=[prior_id])
        self.save_record(self.a, record)
        self.transcript(record, cli_id=prior_id)
        plan = self.plan()
        self.assertEqual(len(self.catalog_changes(plan)), 1)
        copied = json.loads(base64.b64decode(self.catalog_changes(plan)[0]["data_b64"]))
        self.assertEqual(copied["cliSessionId"], record["cliSessionId"])
        self.assertEqual(copied["priorCliSessionIds"], [prior_id])

    def test_existing_disagreement_is_reported_without_overwrite(self):
        first = self.record()
        other = dict(first, title="Edited independently in B")
        self.save_record(self.a, first)
        self.save_record(self.b, other)
        self.transcript(first)
        before = self.snapshot()
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["conflicts"])
        self.assertEqual(self.snapshot(), before)

    def test_tombstone_prevents_resurrection_in_destination(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        tombstone = self.b / record["sessionId"].replace("local_", "deleted_", 1)
        tombstone.write_text("", encoding="utf-8")
        before = self.snapshot()
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertTrue(plan["tombstone_skips"])
        self.assertEqual(self.snapshot(), before)

    def test_archive_index_agrees_with_the_copied_record(self):
        record = self.record(isArchived=True)
        self.save_record(self.a, record)
        self.transcript(record)
        (self.a / "archived-sessions.idx").write_text(
            json.dumps({"v": 1, "archived": [record["sessionId"]]}), encoding="utf-8"
        )
        plan = self.plan()
        claude_sync.apply_plan(self.root, plan, self.backup)
        copied = json.loads((self.b / (record["sessionId"] + ".json")).read_text())
        self.assertTrue(copied["isArchived"])
        index = json.loads((self.b / "archived-sessions.idx").read_text())
        self.assertEqual(index["v"], 1)
        self.assertIn(record["sessionId"], index["archived"])
        self.assertEqual(self.plan()["changes"], [])

    def test_archive_index_preserves_unrelated_entries(self):
        record = self.record(isArchived=True)
        self.save_record(self.a, record)
        self.transcript(record)
        unrelated = "local_" + str(uuid.uuid4())
        (self.b / "archived-sessions.idx").write_text(
            json.dumps({"v": 1, "archived": [unrelated]}), encoding="utf-8"
        )
        claude_sync.apply_plan(self.root, self.plan(), self.backup)
        index = json.loads((self.b / "archived-sessions.idx").read_text())
        self.assertIn(unrelated, index["archived"])
        self.assertIn(record["sessionId"], index["archived"])

    def test_scheduled_tasks_and_remote_sessions_remain_untouched(self):
        local = self.record()
        self.save_record(self.a, local)
        self.transcript(local)
        task = self.a / "scheduled-tasks.json"
        task.write_text('{"tasks":[{"title":"Do not migrate"}]}\n', encoding="utf-8")
        remote = self.a / (str(uuid.uuid4()) + ".json")
        remote.write_text('{"sessionId":"remote-session","title":"Cloud conversation"}\n', encoding="utf-8")
        preserved = {task: task.read_bytes(), remote: remote.read_bytes()}
        claude_sync.apply_plan(self.root, self.plan(), self.backup)
        for path, data in preserved.items():
            self.assertEqual(path.read_bytes(), data)
            self.assertFalse((self.b / path.name).exists())

    def test_local_named_ssh_and_wsl_sessions_are_not_copied(self):
        for field, settings in (
            ("sshConfig", {"host": "synthetic-remote-host", "user": "synthetic-user"}),
            ("wslConfig", {"distro": "SyntheticDistro"}),
        ):
            with self.subTest(field=field):
                record = self.record(**{field: settings})
                source = self.save_record(self.a, record)
                self.transcript(record)
                before = self.snapshot()
                plan = self.plan()
                self.assertEqual(self.catalog_changes(plan), [])
                self.assertEqual(self.snapshot(), before)
                self.assertFalse((self.b / source.name).exists())

    def test_skipped_remote_destination_is_never_treated_as_a_missing_record(self):
        record = self.record()
        self.save_record(self.a, record)
        self.save_record(self.b, dict(record, sshConfig={"host": "synthetic-remote-host"}))
        self.transcript(record)
        before = self.snapshot()
        plan = self.plan()
        self.assertEqual(self.catalog_changes(plan), [])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_cwd_fails_without_any_catalog_write(self):
        record = self.record()
        self.transcript(record)
        for invalid in ("relative/project", "", None, 42):
            with self.subTest(cwd=invalid):
                self.save_record(self.a, dict(record, cwd=invalid))
                before = self.snapshot()
                with self.assertRaises((ValueError, RuntimeError, OSError)):
                    self.plan()
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.backup.exists())

    def test_transcript_cuts_are_preserved_in_imported_history(self):
        cuts = [{"uuid": str(uuid.uuid4()), "timestamp": "2026-09-02T00:00:00Z"}]
        record = self.record(transcriptCuts=cuts)
        self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        copied = json.loads(base64.b64decode(self.catalog_changes(plan)[0]["data_b64"]))
        self.assertEqual(copied["transcriptCuts"], cuts)
        claude_sync.apply_plan(self.root, plan, self.backup)
        imported = json.loads((self.b / (record["sessionId"] + ".json")).read_text())
        self.assertEqual(imported["transcriptCuts"], cuts)
        self.assertEqual(self.plan()["changes"], [])
        self.assertEqual(self.plan()["conflicts"], [])

    def test_apply_then_undo_restores_exact_original_bytes(self):
        record = self.record(isArchived=True)
        self.save_record(self.a, record)
        self.transcript(record)
        # Deliberately unusual formatting: restoration is byte exact.
        (self.b / "archived-sessions.idx").write_bytes(b'{ "v" : 1, "archived" : [] }\n')
        before = self.snapshot()
        plan = self.plan()
        self.assertTrue(plan["changes"])
        claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertNotEqual(self.snapshot(), before)
        self.assertTrue(list(self.backup.rglob("*")))
        claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_stale_plan_fails_before_any_catalog_write(self):
        for title in ("First", "Second"):
            record = self.record(title=title)
            self.save_record(self.a, record)
            self.transcript(record)
        plan = self.plan()
        self.assertGreaterEqual(len(plan["changes"]), 2)
        stale = self.root / plan["changes"][-1]["relative_path"]
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text("concurrent change", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_source_metadata_change_after_plan_fails_before_any_write(self):
        record = self.record()
        source = self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        modified = dict(record, title="Source changed after the preview")
        source.write_text(json.dumps(modified), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.backup.exists())

    def test_transcript_change_after_plan_fails_before_any_write(self):
        record = self.record()
        self.save_record(self.a, record)
        transcript = self.transcript(record)
        plan = self.plan()
        content = [json.loads(line) for line in transcript.read_text().splitlines()]
        content[0]["message"]["content"] = "Transcript changed after the preview"
        transcript.write_text("\n".join(json.dumps(line) for line in content) + "\n", encoding="utf-8")
        catalog_before = self.snapshot()
        transcript_before = self.snapshot(self.projects)
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), catalog_before)
        self.assertEqual(self.snapshot(self.projects), transcript_before)
        self.assertFalse(self.backup.exists())

    def test_undo_refuses_to_erase_a_concurrent_edit_and_is_all_or_nothing(self):
        for title in ("First", "Second"):
            record = self.record(title=title)
            self.save_record(self.a, record)
            self.transcript(record)
        plan = self.plan()
        claude_sync.apply_plan(self.root, plan, self.backup)
        tampered = self.root / plan["changes"][-1]["relative_path"]
        tampered.write_text("new content after sync", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_partial_apply_write_failure_rolls_back_catalog(self):
        for title in ("First", "Second"):
            record = self.record(title=title)
            self.save_record(self.a, record)
            self.transcript(record)
        plan = self.plan()
        before = self.snapshot()
        original_write = claude_sync.atomic_write
        writes = 0

        def fail_second_catalog_write(path, data):
            nonlocal writes
            if self.root in path.parents:
                writes += 1
                if writes == 2:
                    raise OSError("Synthetic second-write failure")
            return original_write(path, data)

        with mock.patch.object(claude_sync, "atomic_write", side_effect=fail_second_catalog_write):
            with self.assertRaises(OSError):
                claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "rolled_back")

    def test_partial_undo_write_failure_rolls_back_and_can_be_retried(self):
        record = self.record(isArchived=True)
        self.save_record(self.a, record)
        self.transcript(record)
        (self.b / "archived-sessions.idx").write_text(
            json.dumps({"v": 1, "archived": []}), encoding="utf-8"
        )
        before_apply = self.snapshot()
        claude_sync.apply_plan(self.root, self.plan(), self.backup)
        after_apply = self.snapshot()
        original_write = claude_sync.atomic_write
        failed = False

        def fail_first_index_restore(path, data):
            nonlocal failed
            if self.root in path.parents and path.name == "archived-sessions.idx" and not failed:
                failed = True
                raise OSError("Synthetic archive-restore failure")
            return original_write(path, data)

        with mock.patch.object(claude_sync, "atomic_write", side_effect=fail_first_index_restore):
            with self.assertRaises(OSError):
                claude_sync.undo(self.root, self.backup)
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), after_apply)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "applied")
        claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), before_apply)

    def test_apply_manifest_commit_failure_rolls_back_catalog(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        before = self.snapshot()
        original_write = claude_sync.atomic_write

        def fail_applied_manifest(path, data):
            if path == self.backup / "manifest.json" and json.loads(data)["state"] == "applied":
                raise OSError("Synthetic manifest-commit failure")
            return original_write(path, data)

        with mock.patch.object(claude_sync, "atomic_write", side_effect=fail_applied_manifest):
            with self.assertRaises(OSError):
                claude_sync.apply_plan(self.root, self.plan(), self.backup)
        self.assertEqual(self.snapshot(), before)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "rolled_back")

    def test_undo_manifest_commit_failure_rolls_back_and_can_be_retried(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        before_apply = self.snapshot()
        claude_sync.apply_plan(self.root, self.plan(), self.backup)
        after_apply = self.snapshot()
        original_write = claude_sync.atomic_write

        def fail_undone_manifest(path, data):
            if path == self.backup / "manifest.json" and json.loads(data)["state"] == "undone":
                raise OSError("Synthetic undo-manifest failure")
            return original_write(path, data)

        with mock.patch.object(claude_sync, "atomic_write", side_effect=fail_undone_manifest):
            with self.assertRaises(OSError):
                claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), after_apply)
        manifest = json.loads((self.backup / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "applied")
        claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), before_apply)

    def test_malformed_change_data_fails_before_any_catalog_write(self):
        for title in ("First", "Second"):
            record = self.record(title=title)
            self.save_record(self.a, record)
            self.transcript(record)
        plan = copy.deepcopy(self.plan())
        plan["changes"][-1]["data_b64"] = "invalid base64 @@@"
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_path_traversal_in_plan_is_rejected_without_writing(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        plan = copy.deepcopy(self.plan())
        plan["changes"][0]["relative_path"] = "../escaped.json"
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.base / "escaped.json").exists())

    def test_symlinked_destination_is_rejected_without_writing(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        outside = self.base / "outside"
        outside.mkdir()
        self.b.rmdir()
        create_symlink(self, self.b, outside, directory=True)
        before = self.snapshot()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_backup_is_never_replaced(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        self.backup.mkdir()
        sentinel = self.backup / "existing-backup.txt"
        sentinel.write_text("Preserve older recovery data", encoding="utf-8")
        before = self.snapshot()
        backup_before = self.snapshot(self.backup)
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.snapshot(self.backup), backup_before)

    def test_live_catalog_guard_blocks_apply_before_any_write(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        plan = self.plan()
        before = self.snapshot()
        # Mock the live location so this safety check still touches only temporary data.
        with mock.patch.object(claude_sync, "LIVE_ROOT", self.root):
            with self.assertRaises(RuntimeError):
                claude_sync.apply_plan(self.root, plan, self.backup)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.backup.exists())

    def test_live_catalog_guard_blocks_undo_before_any_write(self):
        record = self.record()
        self.save_record(self.a, record)
        self.transcript(record)
        claude_sync.apply_plan(self.root, self.plan(), self.backup)
        before = self.snapshot()
        with mock.patch.object(claude_sync, "LIVE_ROOT", self.root):
            with self.assertRaises(RuntimeError):
                claude_sync.undo(self.root, self.backup)
        self.assertEqual(self.snapshot(), before)

    def test_sandbox_destination_inside_live_config_is_rejected(self):
        synthetic_home = self.base / "synthetic-home"
        destination = synthetic_home / ".claude" / "projects" / "sandbox"
        with mock.patch.object(Path, "home", return_value=synthetic_home):
            with self.assertRaises(RuntimeError):
                claude_sync.create_sandbox(destination)
        self.assertFalse(synthetic_home.exists())

    def test_atomic_write_cannot_bypass_the_live_data_guard(self):
        protected = self.base / "synthetic-live-app"
        protected.mkdir()
        path = protected / "any-data.json"
        path.write_text("Existing data", encoding="utf-8")
        with mock.patch.object(claude_sync, "LIVE_APP_DATA", protected):
            with self.assertRaises(RuntimeError):
                claude_sync.atomic_write(path, b"Replacement")
        self.assertEqual(path.read_text(), "Existing data")


if __name__ == "__main__":
    unittest.main()
