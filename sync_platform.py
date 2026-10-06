"""Platform-specific data locations, process checks and synchronization locks."""
from __future__ import annotations

import csv
import errno
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass


IS_WINDOWS = os.name == "nt"
LINUX_CLAUDE_EXECUTABLE = Path("/usr/lib/claude-desktop/claude-desktop")


def platform_name(*, windows=None, platform=None):
    if platform is not None:
        return platform
    if windows is True or (windows is None and IS_WINDOWS):
        return "win32"
    return "darwin" if windows is False and sys.platform == "win32" else sys.platform


def xdg_directory(name, fallback, *, environ):
    """The XDG specification ignores relative base-directory overrides."""
    value = environ.get(name)
    return Path(value) if value and Path(value).is_absolute() else fallback


def conventional_app_data(*, home=None, environ=None, windows=None, platform=None) -> Path:
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    platform = platform_name(windows=windows, platform=platform)
    if platform == "win32":
        return Path(environ.get("APPDATA") or home / "AppData/Roaming") / "Claude"
    if platform == "linux":
        selected = environ.get("CLAUDE_USER_DATA_DIR")
        if selected and Path(selected).is_absolute():
            return Path(selected)
        return xdg_directory("XDG_CONFIG_HOME", home / ".config", environ=environ) / "Claude"
    return home / "Library/Application Support/Claude"


def default_app_data(*, home=None, environ=None, windows=None, platform=None, strict=True) -> Path:
    """Find one existing Windows catalogue, refusing ambiguous installations.

    The non-strict mode is only used for import-time constants. The CLI performs
    strict discovery after parsing its explicit --app-data override.
    """
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    platform = platform_name(windows=windows, platform=platform)
    conventional = conventional_app_data(home=home, environ=environ, platform=platform)
    if platform != "win32":
        return conventional
    packages = Path(environ.get("LOCALAPPDATA") or home / "AppData/Local") / "Packages"
    candidates = [conventional]
    if packages.is_dir():
        for package in sorted(packages.iterdir()):
            if package.name.casefold().startswith("claude_"):
                candidates.append(package / "LocalCache/Roaming/Claude")
    existing = [path for path in candidates if (path / "claude-code-sessions").is_dir()]
    # A redirected and conventional path may refer to the same location.
    unique = {str(path.resolve()).casefold(): path for path in existing}
    if len(unique) > 1:
        if strict:
            raise ValueError("More than one Claude data directory was found. Use --app-data to select one.")
        return conventional
    return next(iter(unique.values()), conventional)


def sync_storage_directory(*, home=None, environ=None, windows=None, platform=None) -> Path:
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    platform = platform_name(windows=windows, platform=platform)
    if platform == "win32":
        return Path(environ.get("LOCALAPPDATA") or home / "AppData/Local") / "Claude Code User Sync"
    if platform == "linux":
        return xdg_directory("XDG_DATA_HOME", home / ".local/share", environ=environ) / "Claude Code User Sync"
    # Retain the original directory so existing builds share the same lock.
    return home / "Library/Application Support/Claude Account Sync"


def windows_process_encoding():
    """tasklist uses the native OEM code page, independently of Python UTF-8 mode."""
    if os.name != "nt":
        return "utf-8"  # Enables deterministic mocked Windows checks on macOS.
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetOEMCP.argtypes = ()
    api.GetOEMCP.restype = wintypes.UINT
    return f"cp{api.GetOEMCP()}"


@dataclass(frozen=True)
class LinuxProcessState:
    desktop: frozenset[int]
    main: frozenset[int]
    any_claude: bool


def linux_process_identity(pid, *, proc_root=Path("/proc"), uid=None):
    """Read native executable identity and NUL-separated arguments without a shell."""
    uid = os.getuid() if uid is None else uid
    root = Path(proc_root) / str(pid)
    if root.stat().st_uid != uid:
        raise PermissionError("Process belongs to another user")
    executable = os.readlink(root / "exe").removesuffix(" (deleted)")
    with (root / "cmdline").open("rb") as handle:
        command = handle.read(65_537)
    if not command or len(command) > 65_536 or not command.endswith(b"\0"):
        raise ValueError("Invalid process arguments")
    return Path(executable), command[:-1].split(b"\0")


def verified_linux_main(pid, *, proc_root=Path("/proc"), uid=None,
                        expected_executable=LINUX_CLAUDE_EXECUTABLE):
    executable, arguments = linux_process_identity(pid, proc_root=proc_root, uid=uid)
    return (executable == expected_executable and bool(arguments[0])
            and Path(os.fsdecode(arguments[0])).name == "claude-desktop"
            and not any(argument == b"--type" or argument.startswith(b"--type=")
                        for argument in arguments[1:]))


def linux_process_state(*, run=None, timeout=30, proc_root=Path("/proc"), uid=None,
                        expected_executable=LINUX_CLAUDE_EXECUTABLE):
    """Find this user's Desktop and CLI processes, failing closed on uncertainty."""
    run = subprocess.run if run is None else run
    uid = os.getuid() if uid is None else uid
    try:
        result = run(["/bin/ps", "-u", str(uid), "-o", "pid=,comm="],
                     capture_output=True, text=True, check=True, timeout=timeout)
        if result.returncode or not isinstance(result.stdout, str) or not result.stdout.strip():
            raise ValueError("Invalid process listing")
        desktop, main, any_claude = set(), set(), False
        for line in result.stdout.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) != 2 or not parts[0].isdigit() or int(parts[0]) <= 0:
                raise ValueError("Invalid process listing")
            pid, name = int(parts[0]), parts[1].casefold()
            if name not in ("claude-desktop", "claude", "node", "nodejs"):
                continue
            try:
                executable, arguments = linux_process_identity(pid, proc_root=proc_root, uid=uid)
            except FileNotFoundError:
                # A process that exited after the snapshot cannot write catalogs.
                continue
            if name in ("node", "nodejs"):
                if any(b"/@anthropic-ai/claude-code/" in argument
                       or Path(os.fsdecode(argument)).name == "claude"
                       for argument in arguments[1:2]):
                    any_claude = True
                continue
            any_claude = True
            if name == "claude-desktop" or executable.name == "claude-desktop":
                desktop.add(pid)
                if verified_linux_main(pid, proc_root=proc_root, uid=uid,
                                       expected_executable=expected_executable):
                    main.add(pid)
        return LinuxProcessState(frozenset(desktop), frozenset(main), any_claude)
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError) as error:
        raise RuntimeError("Could not verify that Claude is closed. No live changes are allowed.") from error


def assert_claude_closed(*, windows=None, platform=None, run=None):
    platform = platform_name(windows=windows, platform=platform)
    if platform == "linux":
        if linux_process_state(run=run).any_claude:
            raise RuntimeError("Quit Claude completely and finish any running Claude Code processes before syncing.")
        return
    windows = platform == "win32"
    run = subprocess.run if run is None else run
    command = ["tasklist", "/FO", "CSV", "/NH"] if windows else ["ps", "-axo", "comm="]
    try:
        options = {"encoding": windows_process_encoding()} if windows else {}
        result = run(command, capture_output=True, text=True, check=True, timeout=30, **options)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise RuntimeError("Could not verify that Claude is closed. No live changes are allowed.") from error
    if result.returncode != 0:
        raise RuntimeError("Could not verify that Claude is closed. No live changes are allowed.")
    if not isinstance(result.stdout, str) or not result.stdout.strip():
        raise RuntimeError("Could not read the process list. No live changes are allowed.")
    if windows:
        try:
            rows = list(csv.reader(io.StringIO(result.stdout.lstrip("\ufeff")), strict=True))
            rows = [row for row in rows if row]
            if not rows or any(len(row) != 5 or not row[1].isdigit() for row in rows):
                raise ValueError("Invalid process listing")
        except (csv.Error, ValueError, TypeError) as error:
            raise RuntimeError("Could not read the Windows process list. No live changes are allowed.") from error
        if any(row[0].strip().casefold() == "claude.exe" for row in rows):
            raise RuntimeError("Quit Claude completely and finish any running Claude Code processes before syncing.")
        return
    for name in result.stdout.splitlines():
        name = name.strip()
        if name.endswith("/Helpers/chrome-native-host"):
            continue
        if ("/Claude.app/Contents/" in name or "/Claude/claude-code/" in name
                or name.endswith("/.local/bin/claude")):
            raise RuntimeError("Quit Claude completely with Cmd+Q before syncing.")


def lock_file(handle, *, windows=None):
    """Take a nonblocking lock; callers keep the open handle until unlocking."""
    windows = IS_WINDOWS if windows is None else windows
    if windows:
        msvcrt = importlib.import_module("msvcrt")
        # msvcrt locks from the current file position. All processes lock byte 0.
        # Windows permits locking beyond EOF, so no initial write can race with
        # an already-held byte lock.
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            # Some compatible Windows CRTs report an undefined errno (0) on a
            # failed acquisition. Keep writes blocked and treat the lock state
            # as occupied; reopening Claude while it is uncertain is unsafe.
            if error.errno in (0, errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise BlockingIOError("Synchronization lock is held.") from error
            raise
    else:
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_file(handle, *, windows=None):
    windows = IS_WINDOWS if windows is None else windows
    if windows:
        msvcrt = importlib.import_module("msvcrt")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(handle, fcntl.LOCK_UN)
