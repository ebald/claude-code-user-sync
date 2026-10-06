"""Electron bridge checks against synthetic files and mocked application drivers."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from desktop import backend
import claude_sync
from tests.support import create_symlink


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="electron-backend-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.app_data = self.base / "Claude"
        self.projects = self.base / "projects"
        self.storage = self.base / "storage"
        self.driver = backend.DesktopBackend(app_data=self.app_data, projects_dir=self.projects,
                                             storage_dir=self.storage, platform="darwin")

    def profile(self, account, organization):
        directory = self.app_data / "claude-code-sessions" / account / organization
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def make_mac_app(self, *, bundle_id=backend.CLAUDE_BUNDLE_ID):
        application = self.base / "Applications" / "Claude.app"
        (application / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
        (application / "Contents/MacOS/Claude").write_bytes(b"synthetic application fixture")
        (application / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundleIdentifier": bundle_id, "CFBundleExecutable": "Claude"}))
        return application

    def response(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = backend.main(arguments)
        self.assertEqual(errors.getvalue(), "")
        self.assertEqual(len(output.getvalue().splitlines()), 1)
        return status, json.loads(output.getvalue())

    def test_inspection_counts_accounts_once_and_writes_nothing(self):
        self.profile("account-a", "organization-1")
        self.profile("account-a", "organization-2")
        self.profile("account-b", "organization-3")
        with mock.patch.object(backend.subprocess, "run") as run, mock.patch.object(claude_sync, "sync_accounts") as sync:
            value = self.driver.inspect()
        self.assertEqual(value, {"accounts": 2, "lastSync": None, "storageDir": str(self.storage)})
        self.assertFalse(self.storage.exists())
        run.assert_not_called()
        sync.assert_not_called()

    def test_missing_catalog_is_zero_accounts(self):
        self.assertEqual(self.driver.inspect()["accounts"], 0)

    def test_preview_account_inspection_never_reads_saved_history(self):
        self.profile("account-a", "organization")
        with mock.patch.object(backend, "read_last_sync") as read:
            value = self.driver.inspect(accounts_only=True)
        self.assertEqual(value["accounts"], 1)
        self.assertIsNone(value["lastSync"])
        read.assert_not_called()
        with mock.patch.object(backend, "read_last_sync") as read:
            status, response = self.response(["inspect", "--accounts-only", "--app-data", str(self.app_data),
                                             "--storage-dir", str(self.storage)])
        self.assertEqual(status, 0)
        self.assertEqual(response["value"]["accounts"], 1)
        read.assert_not_called()

    def test_symlinked_profiles_do_not_inflate_account_count(self):
        self.profile("real-account", "organization")
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "organization").mkdir()
        link = self.app_data / "claude-code-sessions/fake-account"
        create_symlink(self, link, outside, directory=True)
        self.assertEqual(self.driver.inspect()["accounts"], 1)

    def test_swift_history_date_is_preserved_and_private_fields_are_filtered(self):
        self.storage.mkdir()
        (self.storage / "last-sync.json").write_text(json.dumps({
            "date": 0, "result": {"accounts": 2, "chats": 17, "profiles": 3,
                                   "backup": str(self.storage / "Backups/synthetic"),
                                   "assets": {"local_images": 4, "private_text": "secret"},
                                   "private_record": {"message": "secret"}}}), encoding="utf-8")
        value = self.driver.inspect()["lastSync"]
        self.assertEqual(value["date"], "2001-01-01T00:00:00+00:00")
        self.assertEqual(value["result"]["accounts"], 2)
        self.assertNotIn("private_record", value["result"])
        self.assertNotIn("private_text", value["result"]["assets"])

    def test_malformed_history_and_linked_history_are_ignored(self):
        self.storage.mkdir()
        history = self.storage / "last-sync.json"
        history.write_text("not json", encoding="utf-8")
        self.assertIsNone(self.driver.inspect()["lastSync"])
        history.unlink()
        outside = self.base / "private.json"
        outside.write_text('{"date":"now","result":{"chats":900}}', encoding="utf-8")
        create_symlink(self, history, outside)
        self.assertIsNone(self.driver.inspect()["lastSync"])

    def test_preflight_checks_catalog_installation_and_backup_scope_before_close(self):
        self.profile("account-a", "organization-1")
        self.profile("account-b", "organization-2")
        with mock.patch.object(claude_sync, "configure_live_paths") as configure, \
                mock.patch.object(self.driver, "launch_target", return_value=("app", "fixture")) as launch, \
                mock.patch.object(self.driver, "close") as close:
            result = self.driver.preflight()
        configure.assert_called_once_with(self.app_data, self.projects)
        launch.assert_called_once()
        close.assert_not_called()
        self.assertEqual(result["accounts"], 2)
        self.assertTrue((self.storage / "Backups").is_dir())

    def test_invalid_catalog_fails_preflight_without_closing(self):
        profile = self.profile("account-a", "organization-1")
        self.profile("account-b", "organization-2")
        (profile / "local_not-a-session.json").write_text('{"private":"secret"}', encoding="utf-8")
        with mock.patch.object(claude_sync, "configure_live_paths"), \
                mock.patch.object(self.driver, "close") as close, \
                mock.patch.object(self.driver, "launch_target") as launch:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.preflight()
        self.assertEqual(caught.exception.code, "CATALOG_INVALID")
        close.assert_not_called()
        launch.assert_not_called()
        self.assertFalse(self.storage.exists())

    def test_missing_catalog_fails_preflight_before_launch(self):
        with mock.patch.object(self.driver, "launch_target") as launch:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.preflight()
        self.assertEqual(caught.exception.code, "NO_CHATS")
        launch.assert_not_called()

    def test_explicit_mac_application_must_have_claude_bundle_identifier(self):
        path = self.make_mac_app()
        self.assertEqual(backend.discover_mac_application(path), ("app", str(path)))
        self.make_mac_app(bundle_id="com.example.other")
        with self.assertRaises(backend.BackendError) as caught:
            backend.discover_mac_application(path)
        self.assertEqual(caught.exception.code, "CLAUDE_NOT_FOUND")

    def test_mac_discovery_uses_fixed_launchservices_script(self):
        path = self.make_mac_app()
        completed = subprocess.CompletedProcess([], 0, str(path) + "\n", "")
        with mock.patch.object(backend, "validate_mac_application", side_effect=[backend.BackendError("CLAUDE_NOT_FOUND"),
                                                                               backend.BackendError("CLAUDE_NOT_FOUND"),
                                                                               ("app", str(path))]), \
                mock.patch.object(backend.subprocess, "run", return_value=completed) as run:
            self.assertEqual(backend.discover_mac_application(home=self.base), ("app", str(path)))
        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["/usr/bin/osascript", "-e"])
        self.assertIn(backend.CLAUDE_BUNDLE_ID, command[2])

    def test_windows_discovery_supports_msix_and_explicit_exe(self):
        exe = self.base / "Claude.exe"
        exe.write_bytes(b"synthetic executable")
        self.assertEqual(backend.discover_windows_application(exe), ("exe", str(exe)))
        completed = subprocess.CompletedProcess([], 0, '"Claude_abc!Claude"', "")
        self.assertEqual(backend.discover_windows_application(run=mock.Mock(return_value=completed)),
                         ("msix", "Claude_abc!Claude"))

    def test_windows_discovery_does_not_forward_ambiguous_start_apps(self):
        completed = subprocess.CompletedProcess([], 0, '["Claude_a!App","Claude_b!App"]', "")
        with self.assertRaises(backend.BackendError) as caught:
            backend.discover_windows_application(environ={"LOCALAPPDATA": str(self.base)},
                                                run=mock.Mock(return_value=completed))
        self.assertEqual(caught.exception.code, "CLAUDE_NOT_FOUND")

    def test_windows_process_listing_is_oem_decoded_and_fails_closed(self):
        completed = subprocess.CompletedProcess([], 0, '"CLAUDE.EXE","42","Console","1","1 K"\n"other.exe","7","Console","1","2 K"', "")
        run = mock.Mock(return_value=completed)
        self.assertEqual(backend.windows_process_ids(run=run), {42})
        self.assertEqual(run.call_args.kwargs["encoding"], backend.sync_platform.windows_process_encoding())
        for invalid in ("", "not a process list", '"Claude.exe","bad","Console","1","1 K"'):
            with self.subTest(invalid=invalid):
                with self.assertRaises(backend.BackendError) as caught:
                    backend.windows_process_ids(run=mock.Mock(return_value=subprocess.CompletedProcess([], 0, invalid, "")))
                self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")

    def test_mac_process_listing_includes_cli_and_excludes_native_host(self):
        completed = subprocess.CompletedProcess([], 0, "/Applications/Claude.app/Contents/Helpers/chrome-native-host\n/bin/launchd\n", "")
        self.assertEqual(backend.mac_process_state(run=mock.Mock(return_value=completed)), (False, False))
        completed.stdout += "/Users/example/.local/bin/claude\n"
        self.assertEqual(backend.mac_process_state(run=mock.Mock(return_value=completed)), (False, True))

    def test_mac_shutdown_only_requests_normal_quit_and_waits(self):
        with mock.patch.object(backend, "mac_process_state", side_effect=[(True, True), (False, False)]), \
                mock.patch.object(backend.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(self.driver.close(), {"closed": True})
        self.assertEqual(run.call_args.args[0], ["/usr/bin/osascript", "-e",
                                               f'tell application id "{backend.CLAUDE_BUNDLE_ID}" to quit'])

    def test_windows_shutdown_requests_only_existing_claude_pids(self):
        self.driver.platform = "win32"
        with mock.patch.object(backend, "windows_process_ids", side_effect=[{42, 43}, set()]), \
                mock.patch.object(backend, "request_windows_shutdown") as request:
            self.assertEqual(self.driver.close(), {"closed": True})
        request.assert_called_once_with({42, 43})

    def test_shutdown_timeout_never_terminates_or_reopens(self):
        with mock.patch.object(backend, "mac_process_state", return_value=(False, True)), \
                mock.patch.object(backend.time, "monotonic", side_effect=[0, 31]), \
                mock.patch.object(backend.subprocess, "run") as run, \
                mock.patch.object(self.driver, "open") as reopen:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "CLOSE_FAILED")
        run.assert_not_called()
        reopen.assert_not_called()

    def test_process_check_failure_never_requests_shutdown(self):
        with mock.patch.object(backend, "mac_process_state", side_effect=backend.BackendError("PROCESS_CHECK_FAILED")), \
                mock.patch.object(backend.subprocess, "run") as run:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")
        run.assert_not_called()

    def test_sync_saves_summary_before_separate_open_action(self):
        result = {"accounts": 2, "chats": 12, "projects": 4,
                  "backup": str(self.storage / "Backups/sync-example/backup"),
                  "assets": {"diagnostic_version": 2, "local_files": 3}}
        with mock.patch.object(claude_sync, "configure_live_paths") as configure, \
                mock.patch.object(claude_sync, "sync_accounts", return_value=result) as sync, \
                mock.patch.object(self.driver, "open") as reopen:
            value = self.driver.sync()
        configure.assert_called_once_with(self.app_data, self.projects)
        sync.assert_called_once_with(self.storage / "Backups")
        reopen.assert_not_called()
        saved = json.loads((self.storage / "last-sync.json").read_bytes())
        self.assertEqual(saved, {"date": value["date"], "result": result})
        self.assertIsNone(value["saveError"])

    def test_completed_sync_is_preserved_if_history_cannot_be_saved(self):
        result = {"accounts": 2, "chats": 12, "backup": "synthetic backup"}
        with mock.patch.object(claude_sync, "configure_live_paths"), \
                mock.patch.object(claude_sync, "sync_accounts", return_value=result), \
                mock.patch.object(claude_sync, "atomic_write", side_effect=OSError("secret path")):
            value = self.driver.sync()
        self.assertEqual(value["result"], result)
        self.assertEqual(value["saveError"], backend.SAVE_ERROR)
        self.assertNotIn("secret", value["saveError"])

    def test_sync_busy_does_not_save_or_reopen_and_has_distinct_error(self):
        with mock.patch.object(claude_sync, "configure_live_paths"), \
                mock.patch.object(claude_sync, "sync_accounts", side_effect=RuntimeError("Another synchronization is already running. Wait for it to finish.")), \
                mock.patch.object(claude_sync, "atomic_write") as save, \
                mock.patch.object(self.driver, "open") as reopen:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.sync()
        self.assertEqual(caught.exception.code, "SYNC_BUSY")
        save.assert_not_called()
        reopen.assert_not_called()

    def test_unexpected_sync_error_does_not_expose_private_data(self):
        with mock.patch.object(claude_sync, "configure_live_paths"), \
                mock.patch.object(claude_sync, "sync_accounts", side_effect=ValueError("secret transcript and local filename")):
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.sync()
        self.assertEqual(caught.exception.code, "SYNC_FAILED")
        self.assertNotIn("secret", str(caught.exception))

    def test_open_confirms_desktop_process_not_just_cli_process(self):
        with mock.patch.object(self.driver, "launch_target", return_value=("app", "synthetic Claude.app")), \
                mock.patch.object(claude_sync, "sync_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(backend.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                mock.patch.object(backend, "mac_process_state", side_effect=[(False, True), (True, True)]), \
                mock.patch.object(backend.time, "sleep"):
            self.assertEqual(self.driver.open(), {"opened": True})
        self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-a", "synthetic Claude.app"])

    def test_open_failure_retains_saved_summary(self):
        self.storage.mkdir()
        history = self.storage / "last-sync.json"
        history.write_text('{"date":"2026-01-01T00:00:00Z","result":{"accounts":2}}', encoding="utf-8")
        before = history.read_bytes()
        with mock.patch.object(self.driver, "launch_target", return_value=("app", "fixture")), \
                mock.patch.object(claude_sync, "sync_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(backend.subprocess, "run", side_effect=OSError("secret path")):
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.open()
        self.assertEqual(caught.exception.code, "OPEN_FAILED")
        self.assertEqual(history.read_bytes(), before)

    def test_open_does_not_launch_while_shared_sync_lock_is_held(self):
        # Exercise the native engine lock against a separate file handle, rather
        # than merely simulating a busy error in the Electron state machine.
        with mock.patch.object(backend.sync_platform, "sync_storage_directory", return_value=self.base / "locks"), \
                mock.patch.object(self.driver, "launch_target", return_value=("app", "fixture")), \
                mock.patch.object(backend.subprocess, "run") as run, \
                mock.patch.object(backend.subprocess, "Popen") as popen:
            with claude_sync.sync_lock():
                with self.assertRaises(backend.BackendError) as caught:
                    self.driver.open()
        self.assertEqual(caught.exception.code, "SYNC_BUSY")
        run.assert_not_called()
        popen.assert_not_called()

    def test_open_holds_shared_lock_until_desktop_launch_is_confirmed(self):
        events = []

        @contextlib.contextmanager
        def lock():
            events.append("locked")
            yield
            events.append("unlocked")

        def launch(*args, **kwargs):
            self.assertEqual(events, ["locked"])
            events.append("launched")
            return subprocess.CompletedProcess([], 0)

        def running(**kwargs):
            self.assertEqual(events, ["locked", "launched"])
            events.append("confirmed")
            return True, True

        with mock.patch.object(self.driver, "launch_target", return_value=("app", "fixture")), \
                mock.patch.object(claude_sync, "sync_lock", lock), \
                mock.patch.object(backend.subprocess, "run", launch), \
                mock.patch.object(backend, "mac_process_state", running):
            self.assertEqual(self.driver.open(), {"opened": True})
        self.assertEqual(events, ["locked", "launched", "confirmed", "unlocked"])

    def test_help_is_json_success_and_never_initializes_driver(self):
        with mock.patch.object(backend, "DesktopBackend") as driver:
            status, response = self.response(["--help"])
        self.assertEqual(status, 0)
        self.assertTrue(response["ok"])
        self.assertIn("inspect", response["value"]["actions"])
        driver.assert_not_called()

    def test_bridge_protocol_is_json_on_invalid_argument_and_unexpected_error(self):
        status, response = self.response(["invalid-action", "secret argument"])
        self.assertEqual(status, 1)
        self.assertEqual(response["error"]["code"], "INVALID_ARGUMENTS")
        self.assertNotIn("secret", json.dumps(response))
        with mock.patch.object(backend.DesktopBackend, "inspect", side_effect=RuntimeError("secret message")):
            status, response = self.response(["inspect", "--app-data", str(self.app_data), "--storage-dir", str(self.storage)])
        self.assertEqual(status, 1)
        self.assertEqual(response["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("secret", json.dumps(response))

    def test_bridge_suppresses_incidental_core_output(self):
        def inspect(_):
            print("private content")
            print("private errors", file=sys.stderr)
            return {"accounts": 2}
        with mock.patch.object(backend.DesktopBackend, "inspect", inspect):
            status, response = self.response(["inspect", "--app-data", str(self.app_data), "--storage-dir", str(self.storage)])
        self.assertEqual(status, 0)
        self.assertEqual(response, {"ok": True, "value": {"accounts": 2}})

    def test_synthetic_sync_integration_preserves_three_profiles_as_two_accounts(self):
        self.profile("account-a", "organization-1")
        self.profile("account-a", "organization-2")
        self.profile("account-b", "organization-3")
        self.projects.mkdir()
        self.driver.platform = sys.platform
        # Preserve the engine's process-global live scope after this synthetic run.
        names = ("LIVE_APP_DATA", "LIVE_ROOT", "LIVE_PROJECTS", "_PATHS_CONFIGURED", "_LIVE_WRITE_PATHS")
        with contextlib.ExitStack() as stack:
            for name in names:
                stack.enter_context(mock.patch.object(claude_sync, name, getattr(claude_sync, name)))
            stack.enter_context(mock.patch.object(claude_sync, "assert_claude_closed"))
            stack.enter_context(mock.patch.object(backend.sync_platform, "sync_storage_directory", return_value=self.base / "locks"))
            value = self.driver.sync()
        self.assertEqual(value["result"]["accounts"], 2)
        self.assertEqual(value["result"]["profiles"], 3)
        self.assertEqual(value["result"]["chats"], 0)
        self.assertTrue(Path(value["result"]["backup"]).is_dir())
        self.assertEqual(self.driver.inspect()["lastSync"]["result"], value["result"])

    def test_mutating_actions_refuse_unsupported_platform(self):
        self.driver.platform = "linux"
        for action in ("preflight", "close", "sync", "open"):
            with self.subTest(action=action):
                with self.assertRaises(backend.BackendError) as caught:
                    getattr(self.driver, action)()
                self.assertEqual(caught.exception.code, "UNSUPPORTED_PLATFORM")


if __name__ == "__main__":
    unittest.main()
