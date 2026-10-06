"""Build the console-only Python helper on the target host, without user data."""
from pathlib import Path
import argparse
import platform
import json
import re
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[2]
PYINSTALLER = "6.22.3"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=("arm64", "x64"), required=True)
    args = parser.parse_args()
    if sys.platform not in ("darwin", "win32") or sys.version_info < (3, 10):
        parser.error("Build on macOS or Windows using Python 3.10 or newer.")
    machine = platform.machine().lower()
    actual_arch = "arm64" if machine in ("arm64", "aarch64") else "x64" if machine in ("amd64", "x86_64") else machine
    if actual_arch != args.arch:
        parser.error("Python and Node.js must use the same architecture. Select a matching Python with CLAUDE_SYNC_PYTHON.")
    environment = ROOT / ".sandbox/electron-backend" / f"{sys.platform}-{args.arch}" / "venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", f"pyinstaller=={PYINSTALLER}"], check=True)
    subprocess.run([
        str(python), "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console", "--noupx",
        "--name", "claude-sync-backend", "--paths", str(ROOT),
        "--hidden-import", "msvcrt" if sys.platform == "win32" else "fcntl",
        "--distpath", str(ROOT / "desktop/backend-dist"),
        "--workpath", str(ROOT / "desktop/backend-build"),
        "--specpath", str(ROOT / "desktop"),
        str(ROOT / "desktop/backend.py"),
    ], check=True)
    output = ROOT / "desktop/backend-dist/claude-sync-backend"
    info = {"platform": sys.platform, "arch": args.arch}
    if sys.platform == "darwin":
        # A locally built Python may require a newer macOS than Electron does.
        native = []
        for file in output.rglob("*"):
            if file.is_file() and not file.is_symlink():
                with file.open("rb") as stream:
                    magic = stream.read(4)
                if magic in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
                    native.append(str(file))
        headers = subprocess.run(["/usr/bin/otool", "-l", *native], check=True, text=True, capture_output=True).stdout
        versions = re.findall(r"\bminos\s+(\d+(?:\.\d+){0,2})", headers)
        versions.extend(re.findall(r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+){0,2})", headers))
        if not versions:
            raise RuntimeError("Could not determine the packaged Python minimum macOS version.")
        version_key = lambda value: tuple(int(part) for part in value.split(".")) + (0,) * (3 - len(value.split(".")))
        info["minimumMacOS"] = max(["13.0", *versions], key=version_key)
    (output / "build-info.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
