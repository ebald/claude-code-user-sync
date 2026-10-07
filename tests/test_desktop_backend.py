"""Electron bridge checks against synthetic files and mocked application drivers."""
from __future__ import annotations

import contextlib
import ctypes
import errno
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
from types import SimpleNamespace
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

    def test_windows_discovery_ignores_classic_shortcut_alongside_msix(self):
        completed = subprocess.CompletedProcess([], 0,
            '["com.squirrel.AnthropicClaude.Claude","Claude_pzs8sxrjxfjjc!Claude"]', "")
        self.assertEqual(backend.discover_windows_application(
            environ={"LOCALAPPDATA": str(self.base)}, run=mock.Mock(return_value=completed)),
            ("msix", "Claude_pzs8sxrjxfjjc!Claude"))

    def test_windows_discovery_excludes_invalid_package_application_ids(self):
        invalid_ids = ["!Claude", "Claude_abc!", "Claude_abc!App!Other",
                       "shell:Claude_abc!App", "Claude_abc!App/path",
                       "Claude_abc!App\\path", "Claude_abc!App\x00",
                       "Claude_abc!App\r", "Claude_abc!App\n", None, 42]
        for app_id in invalid_ids:
            with self.subTest(app_id=app_id):
                completed = subprocess.CompletedProcess([], 0, json.dumps([app_id]), "")
                with self.assertRaises(backend.BackendError) as caught:
                    backend.discover_windows_application(environ={"LOCALAPPDATA": str(self.base)},
                                                        run=mock.Mock(return_value=completed))
                self.assertEqual(caught.exception.code, "CLAUDE_NOT_FOUND")

    def test_linux_defaults_use_native_platform_locations(self):
        with mock.patch.object(backend.sync_platform, "default_app_data", return_value=self.app_data) as data, \
                mock.patch.object(backend.sync_platform, "sync_storage_directory", return_value=self.storage) as storage:
            driver = backend.DesktopBackend(platform="linux")
        self.assertEqual(driver.app_data, self.app_data)
        data.assert_called_once_with(platform="linux")
        storage.assert_called_once_with(platform="linux")

    def test_linux_discovery_accepts_executable_native_launcher_without_a_shell(self):
        launcher = self.base / "claude-desktop"
        launcher.write_bytes(b"synthetic executable")
        launcher.chmod(0o700)
        self.assertEqual(backend.discover_linux_application(launcher), ("exe", str(launcher)))
        for path in (self.base / "other", self.base / "Claude.exe"):
            path.write_bytes(b"synthetic executable")
            path.chmod(0o700)
            with self.assertRaises(backend.BackendError) as caught:
                backend.discover_linux_application(path)
            self.assertEqual(caught.exception.code, "CLAUDE_NOT_FOUND")
        with mock.patch.object(backend, "validate_linux_executable", side_effect=[backend.BackendError("CLAUDE_NOT_FOUND"),
                                                                                ("exe", "verified fixture")]) as validate:
            self.assertEqual(backend.discover_linux_application(), ("exe", "verified fixture"))
        self.assertEqual(validate.call_args_list[0].args[0], Path("/usr/bin/claude-desktop"))
        self.assertEqual(validate.call_args_list[1].args[0], backend.sync_platform.LINUX_CLAUDE_EXECUTABLE)

    def test_linux_process_errors_use_safe_bridge_error(self):
        with mock.patch.object(backend.sync_platform, "linux_process_state", side_effect=RuntimeError("private path")):
            with self.assertRaises(backend.BackendError) as caught:
                backend.linux_process_state()
        self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")
        self.assertNotIn("private", str(caught.exception))

    def test_linux_normal_quit_binds_signal_to_verified_process_handle(self):
        events = []
        def opened(pid, flags):
            events.append(("opened", pid, flags))
            return 123
        def verified(pid):
            events.append(("verified", pid))
            return True
        def signaled(handle, sig, info, flags):
            events.append(("signaled", handle, sig, info, flags))
        with mock.patch.object(backend.os, "pidfd_open", opened, create=True), \
                mock.patch.object(backend.signal, "pidfd_send_signal", signaled, create=True), \
                mock.patch.object(backend.sync_platform, "verified_linux_main", verified), \
                mock.patch.object(backend.os, "close") as close, \
                mock.patch.object(backend.os, "kill") as kill:
            backend.request_linux_shutdown({42})
        self.assertEqual(events, [("opened", 42, 0), ("verified", 42),
                                  ("signaled", 123, backend.signal.SIGTERM, None, 0)])
        close.assert_called_once_with(123)
        kill.assert_not_called()

    def test_linux_unverified_or_unsupported_shutdown_asks_for_manual_quit(self):
        for verification in (False, PermissionError("private path")):
            with self.subTest(verification=verification), \
                    mock.patch.object(backend.os, "pidfd_open", return_value=123, create=True), \
                    mock.patch.object(backend.signal, "pidfd_send_signal", create=True) as send, \
                    mock.patch.object(backend.sync_platform, "verified_linux_main",
                                      side_effect=verification if isinstance(verification, Exception) else None,
                                      return_value=False), \
                    mock.patch.object(backend.os, "close") as close, \
                    mock.patch.object(backend.os, "kill") as kill:
                with self.assertRaises(backend.BackendError) as caught:
                    backend.request_linux_shutdown({42})
                self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
                send.assert_not_called()
                kill.assert_not_called()
                close.assert_called_once_with(123)
        with mock.patch.object(backend, "hasattr", return_value=False, create=True), \
                mock.patch.object(backend.os, "kill") as kill:
            with self.assertRaises(backend.BackendError) as caught:
                backend.request_linux_shutdown({42})
        self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
        kill.assert_not_called()

    def test_linux_unavailable_kernel_pidfd_and_exited_process_never_use_numeric_signals(self):
        for error in (OSError(errno.ENOSYS, "unavailable"), ProcessLookupError()):
            with self.subTest(error=error), \
                    mock.patch.object(backend.os, "pidfd_open", side_effect=error, create=True), \
                    mock.patch.object(backend.signal, "pidfd_send_signal", create=True) as send, \
                    mock.patch.object(backend.os, "kill") as kill:
                if isinstance(error, ProcessLookupError):
                    backend.request_linux_shutdown({42})
                else:
                    with self.assertRaises(backend.BackendError) as caught:
                        backend.request_linux_shutdown({42})
                    self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
                send.assert_not_called()
                kill.assert_not_called()

    def test_linux_reused_or_unverified_second_pid_prevents_all_shutdown_requests(self):
        with mock.patch.object(backend.os, "pidfd_open", side_effect=[123, 124], create=True), \
                mock.patch.object(backend.signal, "pidfd_send_signal", create=True) as send, \
                mock.patch.object(backend.sync_platform, "verified_linux_main", side_effect=[True, False]), \
                mock.patch.object(backend.os, "close") as close:
            with self.assertRaises(backend.BackendError) as caught:
                backend.request_linux_shutdown({42, 43})
        self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
        send.assert_not_called()
        self.assertEqual(close.call_args_list, [mock.call(123), mock.call(124)])

    def test_linux_close_requests_verified_main_quit_then_waits_for_all_claude_processes(self):
        self.driver.platform = "linux"
        processes = backend.sync_platform.LinuxProcessState(frozenset({42, 43}), frozenset({42}), True)
        closed = backend.sync_platform.LinuxProcessState(frozenset(), frozenset(), False)
        with mock.patch.object(backend, "linux_process_state", side_effect=[processes, processes, closed]), \
                mock.patch.object(backend, "request_linux_shutdown") as request, \
                mock.patch.object(backend.time, "sleep"):
            self.assertEqual(self.driver.close(), {"closed": True})
        request.assert_called_once_with(frozenset({42}))

    def test_linux_cli_or_nonstandard_desktop_requires_manual_quit_without_writes(self):
        self.driver.platform = "linux"
        processes = backend.sync_platform.LinuxProcessState(frozenset(), frozenset(), True)
        with mock.patch.object(backend, "linux_process_state", return_value=processes), \
                mock.patch.object(backend, "request_linux_shutdown") as request, \
                mock.patch.object(claude_sync, "sync_accounts") as sync:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
        request.assert_not_called()
        sync.assert_not_called()

    def test_linux_shutdown_timeout_does_not_force_terminate(self):
        self.driver.platform = "linux"
        processes = backend.sync_platform.LinuxProcessState(frozenset({42}), frozenset({42}), True)
        with mock.patch.object(backend, "linux_process_state", return_value=processes), \
                mock.patch.object(backend, "request_linux_shutdown"), \
                mock.patch.object(backend.time, "monotonic", side_effect=[0, 31]), \
                mock.patch.object(backend.os, "kill") as kill:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "CLAUDE_RUNNING")
        kill.assert_not_called()

    def test_linux_reopen_runs_only_selected_launcher_and_confirms_desktop_under_lock(self):
        self.driver.platform = "linux"
        closed = backend.sync_platform.LinuxProcessState(frozenset(), frozenset(), False)
        opened = backend.sync_platform.LinuxProcessState(frozenset({42}), frozenset({42}), True)
        with mock.patch.object(self.driver, "launch_target", return_value=("exe", "/usr/bin/claude-desktop")), \
                mock.patch.object(claude_sync, "sync_lock", return_value=contextlib.nullcontext()), \
                mock.patch.object(backend.subprocess, "Popen") as launch, \
                mock.patch.object(backend, "linux_process_state", side_effect=[closed, opened]), \
                mock.patch.object(backend.time, "sleep"):
            self.assertEqual(self.driver.open(), {"opened": True})
        self.assertEqual(launch.call_args.args[0], ["/usr/bin/claude-desktop"])
        self.assertNotIn("shell", launch.call_args.kwargs)

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

    def windows_shutdown_apis(self, *, windows=None, processes=None):
        windows = [(101, 42)] if windows is None else windows
        processes = {42: {"image": r"C:\Program Files\Claude\Claude.exe", "session": 1,
                          "created": 123456, "exit": 259}} if processes is None else processes
        window_pids = dict(windows)

        def enum_windows(callback, _):
            for window, _pid in windows:
                callback(window, 0)
            return True

        def window_pid(window, pointer):
            pointer._obj.value = window_pids.get(window, 0)
            return 1 if pointer._obj.value else 0

        def process_session(pid, pointer):
            if pid == 9000:
                pointer._obj.value = 1
                return True
            if pid not in processes:
                return False
            pointer._obj.value = processes[pid]["session"]
            return True

        def process_image(handle, _flags, buffer, length):
            buffer.value = processes[handle - 1000]["image"]
            length._obj.value = len(buffer.value)
            return True

        def process_times(handle, created, _exited, _kernel, _user):
            created._obj.dwLowDateTime = processes[handle - 1000]["created"]
            created._obj.dwHighDateTime = 7
            return True

        def exit_code(handle, pointer):
            pointer._obj.value = processes[handle - 1000]["exit"]
            return True

        def start_session(pointer, _flags, _key):
            pointer._obj.value = 123
            return 0

        return SimpleNamespace(
            callback_factory=ctypes.CFUNCTYPE,
            user32=SimpleNamespace(EnumWindows=mock.Mock(side_effect=enum_windows),
                GetWindowThreadProcessId=mock.Mock(side_effect=window_pid), PostMessageW=mock.Mock(return_value=True)),
            kernel32=SimpleNamespace(GetCurrentProcessId=mock.Mock(return_value=9000),
                ProcessIdToSessionId=mock.Mock(side_effect=process_session),
                OpenProcess=mock.Mock(side_effect=lambda _access, _inherit, pid: pid + 1000 if pid in processes else 0),
                QueryFullProcessImageNameW=mock.Mock(side_effect=process_image),
                GetProcessTimes=mock.Mock(side_effect=process_times), GetExitCodeProcess=mock.Mock(side_effect=exit_code),
                CloseHandle=mock.Mock(return_value=True), TerminateProcess=mock.Mock()),
            restart_manager=SimpleNamespace(RmStartSession=mock.Mock(side_effect=start_session),
                RmRegisterResources=mock.Mock(return_value=0), RmShutdown=mock.Mock(return_value=0),
                RmEndSession=mock.Mock(return_value=0)))

    def test_windows_restart_manager_registers_only_gui_claude_with_creation_time(self):
        native = self.windows_shutdown_apis(windows=[(101, 42), (102, 42), (103, 99)])
        backend.request_windows_shutdown({42, 43}, native=native)
        native.kernel32.OpenProcess.assert_called_once_with(0x1000, False, 42)
        registered = native.restart_manager.RmRegisterResources.call_args.args
        self.assertEqual(registered[:4], (123, 0, None, 1))
        self.assertEqual(registered[5:], (0, None))
        self.assertEqual(registered[4][0].dwProcessId, 42)
        self.assertEqual(registered[4][0].ProcessStartTime.dwLowDateTime, 123456)
        self.assertEqual(registered[4][0].ProcessStartTime.dwHighDateTime, 7)
        native.restart_manager.RmShutdown.assert_called_once_with(123, 0, None)
        native.restart_manager.RmEndSession.assert_called_once_with(123)
        native.kernel32.CloseHandle.assert_called_once_with(1042)
        native.user32.PostMessageW.assert_not_called()
        native.kernel32.TerminateProcess.assert_not_called()

    def test_windows_empty_or_non_gui_processes_do_not_start_shutdown(self):
        for process_ids, windows in ((set(), [(101, 42)]), ({42}, [])):
            with self.subTest(process_ids=process_ids):
                native = self.windows_shutdown_apis(windows=windows)
                backend.request_windows_shutdown(process_ids, native=native)
                native.kernel32.OpenProcess.assert_not_called()
                native.restart_manager.RmStartSession.assert_not_called()
                native.user32.PostMessageW.assert_not_called()

    def test_windows_exited_processes_are_not_registered_or_closed(self):
        for processes in ({}, {42: {"image": r"C:\Claude\Claude.exe", "session": 1,
                                    "created": 1, "exit": 0}}):
            with self.subTest(processes=processes):
                native = self.windows_shutdown_apis(processes=processes)
                backend.request_windows_shutdown({42}, native=native)
                native.restart_manager.RmStartSession.assert_not_called()
                native.user32.PostMessageW.assert_not_called()
                self.assertEqual(native.kernel32.CloseHandle.call_count, len(processes))

    def test_windows_wrong_image_or_session_is_never_signaled(self):
        for image, session in ((r"C:\Other\Other.exe", 1), (r"C:\Claude\Claude.exe", 2)):
            with self.subTest(image=image, session=session):
                native = self.windows_shutdown_apis(processes={42: {
                    "image": image, "session": session, "created": 1, "exit": 259}})
                backend.request_windows_shutdown({42}, native=native)
                native.restart_manager.RmStartSession.assert_not_called()
                native.user32.PostMessageW.assert_not_called()
                native.kernel32.CloseHandle.assert_called_once_with(1042)

    def test_windows_reused_pid_without_original_gui_is_not_registered(self):
        native = self.windows_shutdown_apis()
        original_open = native.kernel32.OpenProcess.side_effect

        def open_replacement(*args):
            handle = original_open(*args)
            native.user32.GetWindowThreadProcessId.side_effect = lambda _window, pointer: (
                setattr(pointer._obj, "value", 99) or 1)
            return handle

        native.kernel32.OpenProcess.side_effect = open_replacement
        backend.request_windows_shutdown({42}, native=native)
        native.restart_manager.RmStartSession.assert_not_called()
        native.user32.PostMessageW.assert_not_called()
        native.kernel32.CloseHandle.assert_called_once_with(1042)

    def test_windows_unavailable_restart_manager_uses_only_normal_window_close(self):
        native = self.windows_shutdown_apis()
        native.restart_manager = None
        backend.request_windows_shutdown({42, 43}, native=native)
        native.user32.PostMessageW.assert_called_once_with(101, 0x0010, 0, 0)
        native.kernel32.CloseHandle.assert_called_once_with(1042)
        native.kernel32.TerminateProcess.assert_not_called()

    def test_windows_restart_manager_failures_fall_back_without_force(self):
        for action, failure in (("RmStartSession", 5), ("RmRegisterResources", 5),
                                ("RmShutdown", 351), ("RmShutdown", OSError("synthetic failure"))):
            with self.subTest(action=action, failure=failure):
                native = self.windows_shutdown_apis()
                function = getattr(native.restart_manager, action)
                function.side_effect = failure if isinstance(failure, Exception) else None
                function.return_value = failure if isinstance(failure, int) else 0
                backend.request_windows_shutdown({42}, native=native)
                native.user32.PostMessageW.assert_called_once_with(101, 0x0010, 0, 0)
                native.kernel32.TerminateProcess.assert_not_called()
                native.kernel32.CloseHandle.assert_called_once_with(1042)
                if action == "RmStartSession":
                    native.restart_manager.RmEndSession.assert_not_called()
                else:
                    native.restart_manager.RmEndSession.assert_called_once_with(123)
                for call in native.restart_manager.RmShutdown.call_args_list:
                    self.assertEqual(call.args, (123, 0, None))

    def test_windows_session_cleanup_failure_still_closes_process_handles(self):
        native = self.windows_shutdown_apis()
        native.restart_manager.RmEndSession.side_effect = OSError("synthetic failure")
        backend.request_windows_shutdown({42}, native=native)
        native.kernel32.CloseHandle.assert_called_once_with(1042)
        native.user32.PostMessageW.assert_not_called()

    def test_windows_window_close_failure_is_safe_and_cleans_resources(self):
        native = self.windows_shutdown_apis()
        native.restart_manager.RmShutdown.return_value = 351
        native.user32.PostMessageW.return_value = False
        with self.assertRaises(backend.BackendError) as caught:
            backend.request_windows_shutdown({42}, native=native)
        self.assertEqual(caught.exception.code, "CLOSE_FAILED")
        native.restart_manager.RmEndSession.assert_called_once_with(123)
        native.kernel32.CloseHandle.assert_called_once_with(1042)
        native.kernel32.TerminateProcess.assert_not_called()

    def test_windows_fallback_does_not_signal_reused_window_or_exited_process(self):
        for change in ("window", "process"):
            with self.subTest(change=change):
                native = self.windows_shutdown_apis()

                def refuse_shutdown(*_):
                    if change == "window":
                        native.user32.GetWindowThreadProcessId.side_effect = lambda _window, pointer: (
                            setattr(pointer._obj, "value", 99) or 1)
                    else:
                        native.kernel32.GetExitCodeProcess.side_effect = lambda _handle, pointer: (
                            setattr(pointer._obj, "value", 0) or True)
                    return 351

                native.restart_manager.RmShutdown.side_effect = refuse_shutdown
                backend.request_windows_shutdown({42}, native=native)
                native.user32.PostMessageW.assert_not_called()
                native.restart_manager.RmEndSession.assert_called_once_with(123)
                native.kernel32.CloseHandle.assert_called_once_with(1042)

    def test_windows_final_poll_timeout_requests_manual_quit_without_other_actions(self):
        self.driver.platform = "win32"
        running = subprocess.CompletedProcess([], 0, '"Claude.exe","42","Console","1","1 K"', "")
        with mock.patch.object(backend.subprocess, "run", side_effect=[
                running, running, subprocess.TimeoutExpired("tasklist", 0.2)]) as run, \
                mock.patch.object(backend, "request_windows_shutdown") as request, \
                mock.patch.object(backend.time, "monotonic", side_effect=[0, 1, 29.8, 30.01]), \
                mock.patch.object(backend.time, "sleep"), \
                mock.patch.object(backend.os, "kill") as kill, \
                mock.patch.object(backend.subprocess, "Popen") as launch, \
                mock.patch.object(self.driver, "open") as reopen, \
                mock.patch.object(claude_sync, "sync_accounts") as sync:
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "CLOSE_FAILED")
        request.assert_called_once_with({42})
        self.assertEqual(run.call_count, 3)
        self.assertAlmostEqual(run.call_args.kwargs["timeout"], 0.2)
        kill.assert_not_called()
        launch.assert_not_called()
        reopen.assert_not_called()
        sync.assert_not_called()
        self.assertFalse(self.storage.exists())

    def test_windows_initial_poll_timeout_does_not_request_shutdown(self):
        self.driver.platform = "win32"
        with mock.patch.object(backend.subprocess, "run", side_effect=subprocess.TimeoutExpired("tasklist", 30)), \
                mock.patch.object(backend, "request_windows_shutdown") as request, \
                mock.patch.object(backend.time, "monotonic", return_value=0):
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")
        request.assert_not_called()
        self.assertFalse(self.storage.exists())

    def test_windows_poll_timeout_before_deadline_stays_process_check_failure(self):
        self.driver.platform = "win32"
        running = subprocess.CompletedProcess([], 0, '"Claude.exe","42","Console","1","1 K"', "")
        with mock.patch.object(backend.subprocess, "run", side_effect=[
                running, subprocess.TimeoutExpired("tasklist", 29)]), \
                mock.patch.object(backend, "request_windows_shutdown") as request, \
                mock.patch.object(backend.time, "monotonic", side_effect=[0, 1, 2]):
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")
        request.assert_called_once_with({42})

    def test_windows_invalid_final_listing_stays_process_check_failure(self):
        self.driver.platform = "win32"
        running = subprocess.CompletedProcess([], 0, '"Claude.exe","42","Console","1","1 K"', "")
        invalid = subprocess.CompletedProcess([], 0, "not a process list", "")
        with mock.patch.object(backend.subprocess, "run", side_effect=[running, invalid]), \
                mock.patch.object(backend, "request_windows_shutdown") as request, \
                mock.patch.object(backend.time, "monotonic", side_effect=[0, 29.8, 30.01]):
            with self.assertRaises(backend.BackendError) as caught:
                self.driver.close()
        self.assertEqual(caught.exception.code, "PROCESS_CHECK_FAILED")
        request.assert_called_once_with({42})

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
        self.driver.platform = "unsupported-test-platform"
        for action in ("preflight", "close", "sync", "open"):
            with self.subTest(action=action):
                with self.assertRaises(backend.BackendError) as caught:
                    getattr(self.driver, action)()
                self.assertEqual(caught.exception.code, "UNSUPPORTED_PLATFORM")


if __name__ == "__main__":
    unittest.main()
