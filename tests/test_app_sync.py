import contextlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import claude_sync as sync
from tests.support import assert_private_mode


class DesktopBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "claude-app" / "claude-code-sessions"
        self.projects = self.base / "claude-config" / "projects"
        self.a = self.root / "a" / "org"
        self.b = self.root / "b" / "org"
        self.a.mkdir(parents=True)
        self.b.mkdir(parents=True)
        self.projects.mkdir(parents=True)
        self.sid = "local_" + str(uuid.uuid4())
        self.cli = str(uuid.uuid4())
        record = {"sessionId": self.sid, "cliSessionId": self.cli, "cwd": str(self.base / "synthetic/project"),
                  "title": "Synthetic", "lastActivityAt": 100, "completedTurns": 2, "permissionMode": "auto"}
        (self.a / (self.sid + ".json")).write_bytes(sync.json_bytes(record))
        project = self.projects / "-synthetic-project"
        project.mkdir()
        (project / (self.cli + ".jsonl")).write_text(json.dumps({"type": "user", "sessionId": self.cli,
            "message": {"role": "user", "content": "Synthetic"}}) + "\n")

    @contextlib.contextmanager
    def isolate(self):
        with patch.object(sync, "LIVE_ROOT", self.root), patch.object(sync, "LIVE_PROJECTS", self.projects), \
             patch.object(sync, "LIVE_APP_DATA", self.root.parent), \
             patch.object(sync, "sync_lock", return_value=contextlib.nullcontext()), \
             patch.object(sync, "assert_claude_closed") as closed:
            yield closed

    def test_desktop_sync_stores_full_backup_and_decodable_result(self):
        before = (self.a / (self.sid + ".json")).read_bytes()
        with self.isolate() as closed:
            result = sync.sync_accounts(self.base / "storage")
            self.assertGreaterEqual(closed.call_count, 3)
            self.assertEqual(result["chats"], 1)
            self.assertEqual(result["accounts"], 2)
            self.assertEqual(result["projects"], 1)
            self.assertEqual(result["copies"], 1)
            backup = Path(result["backup"])
            self.assertTrue((backup / "manifest.json").exists())
            operation = backup.parent
            self.assertEqual((operation / "full-catalogue/a/org" / (self.sid + ".json")).read_bytes(), before)
            self.assertEqual(json.loads((operation / "result.json").read_bytes()), result)
            assert_private_mode(self, operation, 0o700)
            sync.undo(self.root, backup, live=True)
            self.assertFalse((self.b / (self.sid + ".json")).exists())

    def test_second_desktop_sync_has_no_extra_changes(self):
        with self.isolate():
            first = sync.sync_accounts(self.base / "storage")
            second = sync.sync_accounts(self.base / "storage")
        self.assertEqual(first["files_written"], 1)
        self.assertEqual(second["files_written"], 0)
        self.assertEqual(second["chats"], 1)
        self.assertNotEqual(first["backup"], second["backup"])

    def test_desktop_sync_does_not_create_backup_while_claude_running(self):
        with patch.object(sync, "assert_claude_closed", side_effect=RuntimeError("running")):
            with self.assertRaises(RuntimeError):
                sync.sync_accounts(self.base / "storage")
        self.assertFalse((self.base / "storage").exists())

    def test_cross_process_lock_refuses_concurrent_sync(self):
        with patch.object(sync.sync_platform, "sync_storage_directory", return_value=self.base / "locks"):
            with sync.sync_lock():
                with self.assertRaises(RuntimeError):
                    with sync.sync_lock():
                        self.fail("Concurrent sync must never enter")
            with sync.sync_lock():
                pass


if __name__ == "__main__":
    unittest.main()
