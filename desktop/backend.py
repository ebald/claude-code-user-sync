"""Small JSON-only bridge between Electron and the local synchronization engine.

Each invocation performs one action. It never runs a live synchronization merely
to inspect the account count, and never forcibly terminates Claude.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import time

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import claude_sync
import sync_platform
from asset_audit import assert_no_links, is_link

CLAUDE_BUNDLE_ID = "com.anthropic.claudefordesktop"
ERROR_MESSAGES = {
    "INVALID_ARGUMENTS": "The application supplied an invalid request.",
    "UNSUPPORTED_PLATFORM": "The desktop application supports macOS, Windows, and Linux.",
    "PATH_INVALID": "A selected local directory is unavailable or unsafe. Check the application settings.",
    "CLAUDE_NOT_FOUND": "Could not find Claude. Choose its application file and try again.",
    "NO_CHATS": "No local Claude Code chats were found on this computer.",
    "CATALOG_INVALID": "Could not validate the local chat catalogs. No chats were changed.",
    "PROCESS_CHECK_FAILED": "Could not confirm that Claude has closed. No chats were changed.",
    "CLOSE_FAILED": "Claude is still running. Finish any active tasks, close Claude, and try again.",
    "CLAUDE_RUNNING": "Finish any active tasks, quit Claude and any running Claude Code processes, and try again.",
    "OPEN_FAILED": "Claude did not reopen. Use Open Claude to try again.",
    "SYNC_BUSY": "Another synchronization is already running. Wait for it to finish before opening Claude.",
    "SYNC_FAILED": "Synchronization could not finish. Check the backup before trying again.",
    "INSPECT_FAILED": "Could not read the local account information.",
    "INTERNAL_ERROR": "The local operation could not finish. No credentials were changed.",
}
SAVE_ERROR = "Could not save synchronization details. The backup is still available."


class BackendError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(ERROR_MESSAGES[code])


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal error includes command-line values and writes to
        # stderr. Keep the bridge protocol and local paths out of diagnostics.
        raise BackendError("INVALID_ARGUMENTS")


def account_count(app_data):
    """Count accounts, not organization profiles, without opening chat files."""
    root = Path(app_data) / "claude-code-sessions"
    assert_no_links(root)
    accounts = set()
    for profile in root.glob("*/*"):
        if profile.is_dir() and not is_link(profile) and not is_link(profile.parent):
            accounts.add(profile.parent.name)
    return len(accounts)


def read_last_sync(storage):
    """A missing or damaged previous summary must not block account discovery."""
    path = Path(storage) / "last-sync.json"
    try:
        assert_no_links(path)
        if path.stat().st_size > 1_048_576:
            return None
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
            return None
        date = value.get("date")
        if isinstance(date, (int, float)) and not isinstance(date, bool):
            # Swift's default JSONEncoder date is seconds since 2001-01-01.
            date = (datetime(2001, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=date)).isoformat()
        if not isinstance(date, str):
            return None
        # Only return the public summary shape; do not forward unrelated fields
        # from a manually edited or earlier history file to the renderer.
        return {"date": date, "result": result_summary(value["result"])}
    except (OSError, ValueError, TypeError, OverflowError):
        return None


def result_summary(value):
    count_keys = {"accounts", "profiles", "chats", "projects", "files_written",
                  "conflicts", "missing_transcripts", "changes", "skipped_deleted",
                  "artifact_conflicts", "tombstone_skips", "unavailable_copied",
                  "copies", "updates", "archive_indexes", "resolved_conflicts", "writes"}
    result = {key: number for key, number in value.items()
              if key in count_keys and isinstance(number, int) and not isinstance(number, bool) and number >= 0}
    if isinstance(value.get("backup"), str):
        result["backup"] = value["backup"]
    if isinstance(value.get("assets"), dict):
        result["assets"] = {key: number for key, number in value["assets"].items()
                            if isinstance(key, str) and isinstance(number, int)
                            and not isinstance(number, bool) and number >= 0}
    return result


def windows_process_ids(*, run=None, timeout=30):
    run = subprocess.run if run is None else run
    try:
        response = run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True,
                       text=True, encoding=sync_platform.windows_process_encoding(),
                       check=True, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        rows = [row for row in csv.reader(io.StringIO(response.stdout.lstrip("\ufeff")), strict=True) if row]
        if response.returncode or not rows or any(len(row) != 5 or not row[1].isdigit() for row in rows):
            raise ValueError("Invalid process listing")
        return {int(row[1]) for row in rows if row[0].strip().casefold() == "claude.exe"}
    except (OSError, subprocess.SubprocessError, csv.Error, ValueError, TypeError, UnicodeError) as error:
        raise BackendError("PROCESS_CHECK_FAILED") from error


def mac_process_state(*, run=None, timeout=30):
    run = subprocess.run if run is None else run
    try:
        response = run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True,
                       check=True, timeout=timeout)
        if response.returncode or not isinstance(response.stdout, str) or not response.stdout.strip():
            raise ValueError("Invalid process listing")
        names = [line.strip() for line in response.stdout.splitlines()
                 if not line.strip().endswith("/Helpers/chrome-native-host")]
        desktop = any("/Claude.app/Contents/" in name for name in names)
        any_claude = desktop or any("/Claude/claude-code/" in name
                                  or name.endswith("/.local/bin/claude") for name in names)
        return desktop, any_claude
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, UnicodeError) as error:
        raise BackendError("PROCESS_CHECK_FAILED") from error


def linux_process_state(**options):
    try:
        return sync_platform.linux_process_state(**options)
    except RuntimeError as error:
        raise BackendError("PROCESS_CHECK_FAILED") from error


def request_linux_shutdown(process_ids):
    """The official Linux app handles SIGTERM by calling Electron app.quit().

    A pidfd binds each request to the process inspected here, preventing a reused
    numeric PID from receiving a signal. Unsupported kernels/Python versions and
    unverified application builds require the user to quit manually instead.
    """
    if not process_ids:
        return
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise BackendError("CLAUDE_RUNNING")
    handles = []
    try:
        for pid in sorted(process_ids):
            try:
                handle = os.pidfd_open(pid, 0)
            except ProcessLookupError:
                continue
            handles.append(handle)
            try:
                verified = sync_platform.verified_linux_main(pid)
            except FileNotFoundError:
                continue
            if not verified:
                raise BackendError("CLAUDE_RUNNING")
        for handle in handles:
            try:
                signal.pidfd_send_signal(handle, signal.SIGTERM, None, 0)
            except ProcessLookupError:
                pass
    except (OSError, ValueError) as error:
        raise BackendError("CLAUDE_RUNNING") from error
    finally:
        for handle in handles:
            os.close(handle)


def request_windows_shutdown(process_ids):
    if not process_ids:
        return
    import ctypes
    from ctypes import wintypes
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
        user32.EnumWindows.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user32.PostMessageW.restype = wintypes.BOOL
        failures = []

        @callback_type
        def close_window(window, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
            if pid.value in process_ids and not user32.PostMessageW(window, 0x0010, 0, 0):
                failures.append(ctypes.get_last_error())
            return True

        if not user32.EnumWindows(close_window, 0) or failures:
            raise BackendError("CLOSE_FAILED")
    except (OSError, AttributeError) as error:
        raise BackendError("CLOSE_FAILED") from error


def validate_mac_application(path):
    path = Path(path).expanduser().absolute()
    try:
        if path.suffix.lower() != ".app" or not path.is_dir():
            raise ValueError("Not an application")
        metadata = plistlib.loads((path / "Contents/Info.plist").read_bytes())
        executable = metadata.get("CFBundleExecutable")
        if (metadata.get("CFBundleIdentifier") != CLAUDE_BUNDLE_ID
                or not isinstance(executable, str) or not executable
                or Path(executable).name != executable
                or not (path / "Contents/MacOS" / executable).is_file()):
            raise ValueError("Not Claude")
        return ("app", str(path))
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise BackendError("CLAUDE_NOT_FOUND") from error


def discover_mac_application(executable=None, *, home=None, run=None):
    if executable is not None:
        return validate_mac_application(executable)
    home = Path.home() if home is None else Path(home)
    for path in (Path("/Applications/Claude.app"), home / "Applications/Claude.app"):
        try:
            return validate_mac_application(path)
        except BackendError:
            pass
    run = subprocess.run if run is None else run
    # LaunchServices resolves an installed application without opening it.
    script = f'POSIX path of (path to application id "{CLAUDE_BUNDLE_ID}")'
    try:
        response = run(["/usr/bin/osascript", "-e", script], capture_output=True,
                       text=True, check=True, timeout=15)
        return validate_mac_application(response.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError, BackendError) as error:
        raise BackendError("CLAUDE_NOT_FOUND") from error


def validate_windows_executable(path):
    path = Path(path).expanduser().absolute()
    if path.suffix.lower() != ".exe" or path.name.casefold() != "claude.exe" or not path.is_file():
        raise BackendError("CLAUDE_NOT_FOUND")
    return ("exe", str(path))


def discover_windows_application(executable=None, *, environ=None, run=None):
    if executable is not None:
        return validate_windows_executable(executable)
    environ = os.environ if environ is None else environ
    run = subprocess.run if run is None else run
    script = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
              "Get-StartApps | Where-Object {$_.Name -eq 'Claude'} | "
              "Select-Object -ExpandProperty AppID | ConvertTo-Json -Compress")
    try:
        response = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", check=True, timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        app_ids = json.loads(response.stdout) if response.stdout.strip() else []
        app_ids = [app_ids] if isinstance(app_ids, str) else app_ids
        if (isinstance(app_ids, list) and len(app_ids) == 1
                and isinstance(app_ids[0], str) and "!" in app_ids[0]
                and not any(character in app_ids[0] for character in '\\/:\x00\r\n')):
            return ("msix", app_ids[0])
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, UnicodeError):
        pass
    local = Path(environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    roots = [local / "AnthropicClaude", local / "Claude"]
    if environ.get("ProgramFiles"):
        roots.append(Path(environ["ProgramFiles"]) / "Claude")
    for root in roots:
        for path in (root / "Claude.exe", *sorted(root.glob("app-*/Claude.exe"), reverse=True)):
            try:
                return validate_windows_executable(path)
            except BackendError:
                pass
    raise BackendError("CLAUDE_NOT_FOUND")


def validate_linux_executable(path):
    path = Path(path).expanduser().absolute()
    if path.name != "claude-desktop" or not path.is_file() or not os.access(path, os.X_OK):
        raise BackendError("CLAUDE_NOT_FOUND")
    return ("exe", str(path))


def discover_linux_application(executable=None):
    if executable is not None:
        return validate_linux_executable(executable)
    # The official .deb installs this launcher and its native executable. Do not
    # choose an arbitrary command from a mutable PATH or execute a shell.
    for path in (Path("/usr/bin/claude-desktop"), sync_platform.LINUX_CLAUDE_EXECUTABLE):
        try:
            return validate_linux_executable(path)
        except BackendError:
            pass
    raise BackendError("CLAUDE_NOT_FOUND")


class DesktopBackend:
    def __init__(self, *, app_data=None, projects_dir=None, storage_dir=None,
                 claude_executable=None, platform=None):
        self.platform = sys.platform if platform is None else platform
        try:
            self.app_data = Path(app_data).expanduser().absolute() if app_data else sync_platform.default_app_data(platform=self.platform)
            self.projects = Path(projects_dir).expanduser().absolute() if projects_dir else Path.home() / ".claude/projects"
            self.storage = Path(storage_dir).expanduser().absolute() if storage_dir else sync_platform.sync_storage_directory(platform=self.platform)
            assert_no_links(self.app_data)
            assert_no_links(self.projects)
            assert_no_links(self.storage)
        except (OSError, ValueError, RuntimeError) as error:
            raise BackendError("PATH_INVALID") from error
        self.executable = claude_executable

    def supported_platform(self):
        if self.platform not in ("darwin", "win32", "linux"):
            raise BackendError("UNSUPPORTED_PLATFORM")

    def inspect(self, *, accounts_only=False):
        try:
            return {"accounts": account_count(self.app_data),
                    "lastSync": None if accounts_only else read_last_sync(self.storage),
                    "storageDir": str(self.storage)}
        except (OSError, ValueError, RuntimeError) as error:
            raise BackendError("INSPECT_FAILED") from error

    def launch_target(self):
        self.supported_platform()
        if self.platform == "win32":
            return discover_windows_application(self.executable)
        if self.platform == "linux":
            return discover_linux_application(self.executable)
        return discover_mac_application(self.executable)

    def preflight(self):
        self.supported_platform()
        root = self.app_data / "claude-code-sessions"
        if not root.is_dir():
            raise BackendError("NO_CHATS")
        try:
            claude_sync.configure_live_paths(self.app_data, self.projects)
            claude_sync.read_profiles(root)
        except (OSError, ValueError, RuntimeError) as error:
            raise BackendError("CATALOG_INVALID") from error
        self.launch_target()
        try:
            # Check backup scope and writability before asking Claude to close.
            claude_sync.assert_test_root(self.storage)
            claude_sync.private_dir(self.storage)
            claude_sync.private_dir(self.storage / "Backups")
        except (OSError, ValueError, RuntimeError) as error:
            raise BackendError("PATH_INVALID") from error
        return {"accounts": account_count(self.app_data), "storageDir": str(self.storage)}

    def close(self):
        self.supported_platform()
        deadline = time.monotonic() + 30
        if self.platform == "win32":
            request_windows_shutdown(windows_process_ids(timeout=30))
        elif self.platform == "linux":
            processes = linux_process_state(timeout=30)
            if processes.any_claude and not processes.main:
                raise BackendError("CLAUDE_RUNNING")
            request_linux_shutdown(processes.main)
        else:
            desktop, _ = mac_process_state(timeout=30)
            if desktop:
                try:
                    subprocess.run(["/usr/bin/osascript", "-e",
                                    f'tell application id "{CLAUDE_BUNDLE_ID}" to quit'],
                                   capture_output=True, check=True,
                                   timeout=max(0.01, min(15, deadline - time.monotonic())))
                except (OSError, subprocess.SubprocessError) as error:
                    raise BackendError("CLOSE_FAILED") from error
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BackendError("CLAUDE_RUNNING" if self.platform == "linux" else "CLOSE_FAILED")
            running = (bool(windows_process_ids(timeout=remaining)) if self.platform == "win32"
                       else linux_process_state(timeout=remaining).any_claude if self.platform == "linux"
                       else mac_process_state(timeout=remaining)[1])
            if not running:
                return {"closed": True}
            time.sleep(min(0.25, remaining))

    def sync(self):
        self.supported_platform()
        try:
            claude_sync.configure_live_paths(self.app_data, self.projects)
            result = claude_sync.sync_accounts(self.storage / "Backups")
        except (OSError, ValueError, RuntimeError) as error:
            message = str(error)
            if "Another synchronization is already running" in message:
                raise BackendError("SYNC_BUSY") from error
            if any(text in message for text in ("verify that Claude is closed", "read the process list", "read the Windows process list")):
                raise BackendError("PROCESS_CHECK_FAILED") from error
            if "Quit Claude completely" in message:
                raise BackendError("CLAUDE_RUNNING" if self.platform == "linux" else "CLOSE_FAILED") from error
            raise BackendError("SYNC_FAILED") from error
        result = result_summary(result)
        date = datetime.now(timezone.utc).isoformat()
        save_error = None
        try:
            assert_no_links(self.storage / "last-sync.json")
            claude_sync.atomic_write(self.storage / "last-sync.json",
                                     claude_sync.json_bytes({"date": date, "result": result}))
        except (OSError, ValueError, RuntimeError):
            save_error = SAVE_ERROR
        return {"result": result, "date": date, "saveError": save_error}

    def open(self):
        kind, target = self.launch_target()
        try:
            # Use the engine's shared native lock, including the legacy macOS
            # location. A manual Open Claude request must never launch Claude
            # while any CLI, old application or Electron instance is writing.
            with claude_sync.sync_lock():
                if self.platform == "darwin":
                    subprocess.run(["/usr/bin/open", "-a", target], capture_output=True,
                                   check=True, timeout=15)
                elif kind == "msix":
                    os.startfile("shell:AppsFolder\\" + target)
                else:
                    subprocess.Popen([target], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                deadline = time.monotonic() + 8
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise BackendError("OPEN_FAILED")
                    running = (bool(windows_process_ids(timeout=remaining)) if self.platform == "win32"
                               else bool(linux_process_state(timeout=remaining).desktop) if self.platform == "linux"
                               else mac_process_state(timeout=remaining)[0])
                    if running:
                        return {"opened": True}
                    time.sleep(min(0.25, remaining))
        except BackendError as error:
            if error.code == "SYNC_BUSY":
                raise
            raise BackendError("OPEN_FAILED") from error
        except RuntimeError as error:
            if "Another synchronization is already running" in str(error):
                raise BackendError("SYNC_BUSY") from error
            raise BackendError("OPEN_FAILED") from error
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise BackendError("OPEN_FAILED") from error


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    if arguments in (["--help"], ["-h"]):
        print(json.dumps({"ok": True, "value": {
            "usage": "backend action [--app-data PATH] [--projects-dir PATH] [--storage-dir PATH] [--claude-executable PATH]",
            "actions": ["inspect", "preflight", "close", "sync", "open"],
            "accountsOnly": "inspect --accounts-only reads account directory metadata only",
        }}, separators=(",", ":")))
        return 0
    try:
        parser = JSONArgumentParser(add_help=False)
        parser.add_argument("action", choices=("inspect", "preflight", "close", "sync", "open"))
        parser.add_argument("--app-data", type=Path)
        parser.add_argument("--projects-dir", type=Path)
        parser.add_argument("--storage-dir", type=Path)
        parser.add_argument("--claude-executable", type=Path)
        parser.add_argument("--accounts-only", action="store_true")
        options = parser.parse_args(arguments)
        if options.accounts_only and options.action != "inspect":
            raise BackendError("INVALID_ARGUMENTS")
        backend = DesktopBackend(app_data=options.app_data, projects_dir=options.projects_dir,
                                 storage_dir=options.storage_dir, claude_executable=options.claude_executable)
        # Core functions do not usually print, but stdout remains a strict,
        # single-message protocol even if their diagnostics change later.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            value = (backend.inspect(accounts_only=True) if options.accounts_only
                     else getattr(backend, options.action)())
        response = {"ok": True, "value": value}
        status = 0
    except BackendError as error:
        response = {"ok": False, "error": {"code": error.code, "message": str(error)}}
        status = 1
    except Exception:
        response = {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": ERROR_MESSAGES["INTERNAL_ERROR"]}}
        status = 1
    print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
