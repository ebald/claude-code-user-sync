import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import claude_sync as sync


class FullSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "registry"
        self.a = self.root / "a" / "org"
        self.b = self.root / "b" / "org"
        self.a.mkdir(parents=True)
        self.b.mkdir(parents=True)
        self.projects = self.base / "projects"
        self.projects.mkdir()
        self.sid = "local_" + str(uuid.uuid4())
        self.cli = str(uuid.uuid4())
        self.record = {"sessionId": self.sid, "cliSessionId": self.cli,
                       "cwd": str(self.base / "synthetic/project"), "title": "Test", "lastActivityAt": 100,
                       "completedTurns": 3, "permissionMode": "auto", "isArchived": False}

    def put(self, profile, record):
        (profile / (self.sid + ".json")).write_bytes(sync.json_bytes(record))

    def transcript(self):
        directory = self.projects / "-synthetic-project"
        directory.mkdir()
        (directory / (self.cli + ".jsonl")).write_bytes(sync.json_bytes({
            "type": "user", "sessionId": self.cli, "message": {"role": "user", "content": "Synthetic"}}).replace(b"\n", b"" ) + b"\n")

    def test_newest_updates_history_and_preserves_target_settings(self):
        self.transcript()
        self.put(self.a, self.record)
        old = {**self.record, "lastActivityAt": 50, "completedTurns": 1,
               "permissionMode": "plan", "remoteMcpServersConfig": [{"name": "target-only"}]}
        self.put(self.b, old)
        plan = sync.build_plan(self.root, self.projects, resolve_conflicts=True)
        self.assertEqual(plan["summary"]["updates"], 1)
        self.assertEqual(plan["summary"]["resolved_conflicts"], 1)
        sync.apply_plan(self.root, plan, self.base / "backup")
        updated = json.loads((self.b / (self.sid + ".json")).read_bytes())
        self.assertEqual(updated["completedTurns"], 3)
        self.assertEqual(updated["permissionMode"], "plan")
        self.assertEqual(updated["remoteMcpServersConfig"], old["remoteMcpServersConfig"])
        self.assertEqual(sync.build_plan(self.root, self.projects, resolve_conflicts=True)["changes"], [])
        sync.undo(self.root, self.base / "backup")
        self.assertEqual(json.loads((self.b / (self.sid + ".json")).read_bytes()), old)

    def test_equal_timestamp_conflict_is_not_arbitrarily_resolved(self):
        self.put(self.a, self.record)
        self.put(self.b, {**self.record, "title": "Another title"})
        plan = sync.build_plan(self.root, self.projects, resolve_conflicts=True, include_unavailable=True)
        self.assertEqual(plan["summary"]["conflicts"], 1)
        self.assertEqual(plan["changes"], [])

    def test_all_chats_copies_missing_transcript_metadata_without_claiming_recovery(self):
        self.put(self.a, self.record)
        plan = sync.build_plan(self.root, self.projects, include_unavailable=True)
        self.assertEqual(plan["summary"]["copies"], 1)
        self.assertEqual(plan["summary"]["missing_transcripts"], 1)
        sync.apply_plan(self.root, plan, self.base / "backup")
        imported = json.loads((self.b / (self.sid + ".json")).read_bytes())
        self.assertTrue(imported["transcriptUnavailable"])
        self.assertEqual(sync.build_plan(self.root, self.projects, include_unavailable=True)["changes"], [])

    def test_live_flag_requires_exact_live_root_and_closed_app(self):
        self.put(self.a, self.record)
        plan = sync.build_plan(self.root, self.projects, include_unavailable=True)
        with self.assertRaises(ValueError):
            sync.apply_plan(self.root, plan, self.base / "backup", live=True)
        with patch.object(sync, "LIVE_ROOT", self.root), patch.object(sync, "assert_claude_closed", side_effect=RuntimeError("running")):
            with self.assertRaises(RuntimeError):
                sync.apply_plan(self.root, plan, self.base / "backup", live=True)
        self.assertFalse((self.base / "backup").exists())

    def test_live_scope_is_limited_to_planned_paths_and_resets_afterward(self):
        self.put(self.a, self.record)
        plan = sync.build_plan(self.root, self.projects, include_unavailable=True)
        with patch.object(sync, "LIVE_ROOT", self.root), patch.object(sync, "LIVE_APP_DATA", self.root.parent), patch.object(sync, "assert_claude_closed"):
            with sync.live_write_scope(self.root, plan["changes"], True):
                sync.assert_test_root(self.b / (self.sid + ".json"))
                with self.assertRaises(RuntimeError):
                    sync.atomic_write(self.root / "credentials.json", b"{}")
            with self.assertRaises(RuntimeError):
                sync.assert_test_root(self.b / (self.sid + ".json"))

    def test_updates_reject_injected_account_configuration(self):
        self.transcript()
        self.put(self.a, self.record)
        self.put(self.b, {**self.record, "lastActivityAt": 50})
        plan = sync.build_plan(self.root, self.projects, resolve_conflicts=True)
        change = plan["changes"][0]
        obj = json.loads(base64.b64decode(change["data_b64"]))
        obj["remoteMcpServersConfig"] = [{"name": "injected"}]
        change["data_b64"] = base64.b64encode(sync.json_bytes(obj)).decode()
        with self.assertRaises(ValueError):
            sync.apply_plan(self.root, plan, self.base / "backup")


if __name__ == "__main__":
    unittest.main()
