import contextlib
import errno
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

import claude_sync as sync
import sync_platform


class PlatformLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = {"APPDATA": str(self.home / "Roaming"),
                    "LOCALAPPDATA": str(self.home / "Local")}

    def discover(self, **kwargs):
        return sync_platform.default_app_data(home=self.home, environ=self.env, windows=True, **kwargs)

    def msix(self, name="Claude_example"):
        path = self.home / "Local/Packages" / name / "LocalCache/Roaming/Claude"
        (path / "claude-code-sessions").mkdir(parents=True)
        return path

    def test_macos_locations_keep_existing_compatibility_paths(self):
        self.assertEqual(sync_platform.default_app_data(home=self.home, platform="darwin"),
                         self.home / "Library/Application Support/Claude")
        self.assertEqual(sync_platform.sync_storage_directory(home=self.home, platform="darwin"),
                         self.home / "Library/Application Support/Claude Account Sync")

    def test_windows_conventional_and_fallback_locations(self):
        self.assertEqual(self.discover(), self.home / "Roaming/Claude")
        self.assertEqual(sync_platform.default_app_data(home=self.home, environ={}, windows=True),
                         self.home / "AppData/Roaming/Claude")
        self.assertEqual(sync_platform.sync_storage_directory(home=self.home, environ=self.env, windows=True),
                         self.home / "Local/Claude Code User Sync")

    def test_linux_locations_use_xdg_defaults_and_absolute_overrides(self):
        self.assertEqual(sync_platform.default_app_data(home=self.home, environ={}, platform="linux"),
                         self.home / ".config/Claude")
        self.assertEqual(sync_platform.sync_storage_directory(home=self.home, environ={}, platform="linux"),
                         self.home / ".local/share/Claude Code User Sync")
        env = {"XDG_CONFIG_HOME": str(self.home / "config"), "XDG_DATA_HOME": str(self.home / "data")}
        self.assertEqual(sync_platform.default_app_data(home=self.home, environ=env, platform="linux"),
                         self.home / "config/Claude")
        self.assertEqual(sync_platform.sync_storage_directory(home=self.home, environ=env, platform="linux"),
                         self.home / "data/Claude Code User Sync")
        env.update(XDG_CONFIG_HOME="relative", XDG_DATA_HOME="relative")
        self.assertEqual(sync_platform.default_app_data(home=self.home, environ=env, platform="linux"),
                         self.home / ".config/Claude")
        self.assertEqual(sync_platform.sync_storage_directory(home=self.home, environ=env, platform="linux"),
                         self.home / ".local/share/Claude Code User Sync")
        env["CLAUDE_USER_DATA_DIR"] = str(self.home / "explicit-claude-data")
        self.assertEqual(sync_platform.default_app_data(home=self.home, environ=env, platform="linux"),
                         self.home / "explicit-claude-data")

    def test_windows_msix_catalogue_is_selected_without_unrelated_packages(self):
        self.msix("Other_example")
        expected = self.msix("cLaUdE_example")
        self.assertEqual(self.discover(), expected)

    def test_multiple_existing_windows_catalogues_require_explicit_selection(self):
        self.msix()
        conventional = self.home / "Roaming/Claude"
        (conventional / "claude-code-sessions").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "--app-data"):
            self.discover()
        self.assertEqual(self.discover(strict=False), conventional)

    def test_multiple_msix_packages_are_not_chosen_arbitrarily(self):
        self.msix("Claude_one")
        self.msix("Claude_two")
        with self.assertRaisesRegex(ValueError, "--app-data"):
            self.discover()

    def test_explicit_paths_preserve_live_write_scope_and_protect_transcripts(self):
        app_data, projects = self.home / "selected-data", self.home / "shared-projects"
        with mock.patch.multiple(sync, LIVE_APP_DATA=sync.LIVE_APP_DATA,
                                 LIVE_ROOT=sync.LIVE_ROOT, LIVE_PROJECTS=sync.LIVE_PROJECTS,
                                 _PATHS_CONFIGURED=sync._PATHS_CONFIGURED):
            sync.configure_live_paths(app_data, projects)
            self.assertEqual(sync.LIVE_ROOT, app_data / "claude-code-sessions")
            with self.assertRaises(RuntimeError):
                sync.assert_test_root(projects / "project/history.jsonl")
            with mock.patch.object(sync, "assert_claude_closed"):
                with self.assertRaises(ValueError):
                    with sync.live_write_scope(self.home / "other-catalogue", [], live=True):
                        self.fail("A different live root must never be accepted")
                with sync.live_write_scope(sync.LIVE_ROOT, [], live=True):
                    sync.assert_test_root(sync.LIVE_ROOT)
                    with self.assertRaises(RuntimeError):
                        sync.assert_test_root(app_data / "credentials.json")

    def test_global_cli_overrides_reach_sync_without_using_default_discovery(self):
        app_data, projects = self.home / "selected-data", self.home / "shared-projects"
        args = ["claude_sync.py", "--app-data", str(app_data), "--projects-dir", str(projects), "sync", "--live"]
        with mock.patch.multiple(sync, LIVE_APP_DATA=sync.LIVE_APP_DATA,
                                 LIVE_ROOT=sync.LIVE_ROOT, LIVE_PROJECTS=sync.LIVE_PROJECTS,
                                 _PATHS_CONFIGURED=sync._PATHS_CONFIGURED), \
                mock.patch.object(sys, "argv", args), \
                mock.patch.object(sync_platform, "default_app_data", side_effect=ValueError("ambiguous")), \
                mock.patch.object(sync, "sync_accounts", return_value={}) as run, \
                contextlib.redirect_stdout(io.StringIO()):
            sync.main()
            self.assertEqual(sync.LIVE_ROOT, app_data / "claude-code-sessions")
            self.assertEqual(sync.LIVE_PROJECTS, projects)
            run.assert_called_once_with(None)


class ProcessCheckTests(unittest.TestCase):
    @staticmethod
    def result(text, code=0):
        return subprocess.CompletedProcess([], code, stdout=text, stderr="")

    def test_windows_checks_native_claude_names_case_insensitively(self):
        for name in ("Claude.exe", "claude.exe", "CLAUDE.EXE"):
            with self.subTest(name=name):
                run = mock.Mock(return_value=self.result(f'"{name}","12","Console","1","1,024 K"\n'))
                with self.assertRaisesRegex(RuntimeError, "Quit Claude"):
                    sync_platform.assert_claude_closed(windows=True, run=run)
                self.assertEqual(run.call_args.args[0], ["tasklist", "/FO", "CSV", "/NH"])

    def test_windows_complete_listing_without_claude_is_accepted(self):
        run = mock.Mock(return_value=self.result('\ufeff"System","4","Services","0","100 K"\n'
                                                '"python.exe","12","Console","1","2,024 K"\n'))
        sync_platform.assert_claude_closed(windows=True, run=run)

    def test_windows_process_listing_uses_oem_encoding_even_in_python_utf8_mode(self):
        run = mock.Mock(return_value=self.result('"Éditeur.exe","12","Console","1","100 K"\n'))
        with mock.patch.object(sync_platform, "windows_process_encoding", return_value="cp850"):
            sync_platform.assert_claude_closed(windows=True, run=run)
        self.assertEqual(run.call_args.kwargs["encoding"], "cp850")

    def test_process_enumeration_failures_block_live_writes(self):
        for windows in (True, False):
            for error in (FileNotFoundError("missing"), subprocess.CalledProcessError(1, "tasklist"),
                          subprocess.TimeoutExpired("tasklist", 30)):
                with self.subTest(windows=windows, error=type(error).__name__):
                    with self.assertRaisesRegex(RuntimeError, "No live changes"):
                        sync_platform.assert_claude_closed(windows=windows, run=mock.Mock(side_effect=error))
            for result in (self.result("", 0), self.result("unavailable", 1)):
                with self.subTest(windows=windows, result=result.stdout):
                    with self.assertRaisesRegex(RuntimeError, "No live changes"):
                        sync_platform.assert_claude_closed(windows=windows, run=mock.Mock(return_value=result))

    def test_malformed_windows_list_is_not_treated_as_closed(self):
        for listing in ('INFO: no results\n', '"Claude.exe","not-a-pid","Console","1","1 K"\n',
                        '"Claude.exe","12"\n', '"unterminated'):
            with self.subTest(listing=listing):
                with self.assertRaisesRegex(RuntimeError, "No live changes"):
                    sync_platform.assert_claude_closed(windows=True, run=mock.Mock(return_value=self.result(listing)))

    def test_macos_known_desktop_and_cli_processes_are_blocked(self):
        for name in ("/Applications/Claude.app/Contents/MacOS/Claude",
                     "/Applications/Claude.app/Contents/Resources/Claude/claude-code/1/claude",
                     "/synthetic/.local/bin/claude"):
            with self.subTest(name=name):
                with self.assertRaisesRegex(RuntimeError, "Cmd\\+Q"):
                    sync_platform.assert_claude_closed(platform="darwin", run=mock.Mock(return_value=self.result(name)))

    def test_macos_browser_extension_host_does_not_block_sync(self):
        listing = "/Applications/Claude.app/Contents/Helpers/chrome-native-host\n/usr/bin/python3\n"
        sync_platform.assert_claude_closed(platform="darwin", run=mock.Mock(return_value=self.result(listing)))


class LinuxProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proc = Path(self.temp.name)
        self.uid = os.getuid() if hasattr(os, "getuid") else 1000

    def process(self, pid, executable, *arguments):
        root = self.proc / str(pid)
        root.mkdir()
        # os.readlink is mocked so synthetic Windows runs need no symlink privilege.
        (root / "cmdline").write_bytes(b"\0".join(argument.encode() for argument in arguments) + b"\0")
        return executable

    def state(self, listing, identities):
        result = subprocess.CompletedProcess([], 0, listing, "")
        def identity(pid, **_):
            value = identities[pid]
            if isinstance(value, Exception):
                raise value
            return Path(value[0]), [argument.encode() for argument in value[1:]]
        with mock.patch.object(sync_platform, "linux_process_identity", side_effect=identity):
            return sync_platform.linux_process_state(run=mock.Mock(return_value=result), uid=self.uid)

    def test_official_main_helpers_and_cli_have_distinct_roles(self):
        executable = str(sync_platform.LINUX_CLAUDE_EXECUTABLE)
        state = self.state("42 claude-desktop\n43 claude-desktop\n44 claude\n45 node\n46 bash\n", {
            42: (executable, "/usr/bin/claude-desktop"),
            43: (executable, executable, "--type=renderer"),
            44: ("/home/example/.local/share/claude/versions/1", "claude"),
            45: ("/usr/bin/node", "node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"),
        })
        self.assertEqual(state.desktop, frozenset({42, 43}))
        self.assertEqual(state.main, frozenset({42}))
        self.assertTrue(state.any_claude)

    def test_nonstandard_desktop_is_detected_but_never_authorized_for_signaling(self):
        state = self.state("42 claude-desktop\n", {42: ("/tmp/claude-desktop", "claude-desktop")})
        self.assertEqual(state.desktop, frozenset({42}))
        self.assertFalse(state.main)
        self.assertTrue(state.any_claude)

    def test_split_helper_flag_and_empty_main_name_are_not_authorized(self):
        executable = str(sync_platform.LINUX_CLAUDE_EXECUTABLE)
        for arguments in ((executable, "--type", "gpu-process"), ("",)):
            with self.subTest(arguments=arguments):
                state = self.state("42 claude-desktop\n", {42: (executable, *arguments)})
                self.assertFalse(state.main)
                self.assertTrue(state.any_claude)

    def test_exited_candidates_are_ignored_but_unreadable_candidates_block(self):
        self.assertFalse(self.state("42 claude-desktop\n", {42: FileNotFoundError()}).any_claude)
        with self.assertRaisesRegex(RuntimeError, "No live changes"):
            self.state("42 claude-desktop\n", {42: PermissionError()})

    def test_malformed_listings_and_failures_block_live_changes(self):
        for value in ("", "not a process list", "0 claude-desktop", "42"):
            with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "No live changes"):
                self.state(value, {})
        with self.assertRaisesRegex(RuntimeError, "No live changes"):
            sync_platform.linux_process_state(uid=self.uid, run=mock.Mock(side_effect=OSError()))

    def test_cli_processes_block_sync_without_a_desktop_window(self):
        state = self.state("42 node\n", {42: ("/usr/bin/node", "node", "/opt/@anthropic-ai/claude-code/cli.js")})
        self.assertFalse(state.desktop)
        self.assertTrue(state.any_claude)
        with mock.patch.object(sync_platform, "linux_process_state", return_value=state):
            with self.assertRaisesRegex(RuntimeError, "finish any running Claude Code"):
                sync_platform.assert_claude_closed(platform="linux")

    def test_unrelated_node_processes_do_not_block_sync(self):
        self.assertFalse(self.state("42 node\n", {42: ("/usr/bin/node", "node", "/tmp/app.js")}).any_claude)

    def test_node_cli_global_symlink_is_blocked_before_process_title_changes(self):
        for script in ("/usr/local/bin/claude", "/home/example/.local/bin/claude"):
            with self.subTest(script=script):
                state = self.state("42 node\n", {42: ("/usr/bin/node", "node", script)})
                self.assertTrue(state.any_claude)
                self.assertFalse(state.desktop)

    def test_native_identity_keeps_nul_separated_arguments_and_rejects_uncertainty(self):
        self.process(42, "unused", "claude-desktop", "path with spaces", "--type=renderer")
        root = self.proc / "42"
        with mock.patch.object(sync_platform.os, "readlink", return_value="/usr/lib/claude-desktop/claude-desktop (deleted)"), \
                mock.patch.object(Path, "stat", return_value=types.SimpleNamespace(st_uid=self.uid)):
            executable, arguments = sync_platform.linux_process_identity(42, proc_root=self.proc, uid=self.uid)
            self.assertEqual(executable, sync_platform.LINUX_CLAUDE_EXECUTABLE)
            self.assertEqual(arguments, [b"claude-desktop", b"path with spaces", b"--type=renderer"])
            (root / "cmdline").write_bytes(b"missing terminator")
            with self.assertRaises(ValueError):
                sync_platform.linux_process_identity(42, proc_root=self.proc, uid=self.uid)
        with mock.patch.object(Path, "stat", return_value=types.SimpleNamespace(st_uid=self.uid + 1)):
            with self.assertRaises(PermissionError):
                sync_platform.linux_process_identity(42, proc_root=self.proc, uid=self.uid)


class PlatformLockTests(unittest.TestCase):
    def test_windows_locks_and_unlocks_the_same_first_byte_without_writing(self):
        calls = []
        with tempfile.TemporaryFile("a+b") as handle:
            api = types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0,
                                        locking=lambda fd, mode, count: calls.append((os.lseek(fd, 0, 1), mode, count)))
            with mock.patch.object(sync_platform.importlib, "import_module", return_value=api):
                handle.seek(9)
                sync_platform.lock_file(handle, windows=True)
                handle.seek(7)
                sync_platform.unlock_file(handle, windows=True)
            self.assertEqual(calls, [(0, 2, 1), (0, 0, 1)])
            self.assertEqual(os.fstat(handle.fileno()).st_size, 0)

    def test_windows_contention_is_reported_but_other_lock_errors_are_preserved(self):
        for code, expected in ((0, BlockingIOError), (errno.EACCES, BlockingIOError), (errno.EIO, OSError)):
            with self.subTest(code=code), tempfile.TemporaryFile("a+b") as handle:
                api = types.SimpleNamespace(LK_NBLCK=2, locking=mock.Mock(side_effect=OSError(code, "lock error")))
                with mock.patch.object(sync_platform.importlib, "import_module", return_value=api):
                    with self.assertRaises(expected) as error:
                        sync_platform.lock_file(handle, windows=True)
                    if code == errno.EIO:
                        self.assertEqual(error.exception.errno, errno.EIO)

    def test_native_lock_excludes_another_process_and_releases_cleanly(self):
        script = ("import sys, sync_platform\n"
                  "with open(sys.argv[1], 'a+b') as handle:\n"
                  "    try: sync_platform.lock_file(handle)\n"
                  "    except BlockingIOError: sys.exit(7)\n"
                  "    sync_platform.unlock_file(handle)\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync.lock"
            with path.open("a+b") as handle:
                sync_platform.lock_file(handle)
                try:
                    result = subprocess.run([sys.executable, "-c", script, str(path)],
                                            capture_output=True, text=True, timeout=15,
                                            cwd=Path(__file__).resolve().parent.parent)
                    self.assertEqual(result.returncode, 7, result.stderr)
                finally:
                    sync_platform.unlock_file(handle)
                result = subprocess.run([sys.executable, "-c", script, str(path)],
                                        capture_output=True, text=True, timeout=15,
                                        cwd=Path(__file__).resolve().parent.parent)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_undefined_windows_lock_error_never_enters_sync_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            api = types.SimpleNamespace(LK_NBLCK=2, locking=mock.Mock(side_effect=OSError(0, "undefined lock failure")))
            entered = mock.Mock()
            with mock.patch.object(sync_platform, "IS_WINDOWS", True), \
                    mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}), \
                    mock.patch.object(sync_platform.importlib, "import_module", return_value=api):
                with self.assertRaisesRegex(RuntimeError, "Another synchronization"):
                    with sync.sync_lock():
                        entered()
            entered.assert_not_called()


if __name__ == "__main__":
    unittest.main()
