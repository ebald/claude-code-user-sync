"""Packaging architecture checks with synthetic files; no installers run."""
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from desktop.scripts import build_backend


class BackendBuildTests(unittest.TestCase):
    def test_x64_windows_build_uses_interpreter_target_on_arm64_host(self):
        with tempfile.TemporaryDirectory(prefix="backend-build-tests-") as directory:
            root = Path(directory)
            python = root / ".sandbox/electron-backend/win32-x64/venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"synthetic x64 interpreter")
            output = root / "desktop/backend-dist/claude-sync-backend"
            output.mkdir(parents=True)
            runtime = SimpleNamespace(platform="win32", version_info=(3, 14, 8))
            with mock.patch.object(build_backend, "ROOT", root), \
                    mock.patch.object(build_backend, "sys", runtime), \
                    mock.patch("sys.argv", ["build_backend.py", "--arch", "x64"]), \
                    mock.patch.object(build_backend.platform, "machine", return_value="ARM64"), \
                    mock.patch.object(build_backend.sysconfig, "get_platform", return_value="win-amd64"), \
                    mock.patch.object(build_backend.subprocess, "run") as run:
                build_backend.main()
            self.assertEqual(json.loads((output / "build-info.json").read_text()),
                             {"platform": "win32", "arch": "x64"})
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][0], str(python))
                self.assertTrue(call.kwargs["check"])

    def test_non_x64_windows_interpreter_stops_before_installing_build_tools(self):
        for target in ("win-arm64", "win32"):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix="backend-build-tests-") as directory:
                root = Path(directory)
                runtime = SimpleNamespace(platform="win32", version_info=(3, 14, 8))
                errors = io.StringIO()
                with mock.patch.object(build_backend, "ROOT", root), \
                        mock.patch.object(build_backend, "sys", runtime), \
                        mock.patch("sys.argv", ["build_backend.py", "--arch", "x64"]), \
                        mock.patch.object(build_backend.platform, "machine", return_value="AMD64"), \
                        mock.patch.object(build_backend.sysconfig, "get_platform", return_value=target), \
                        mock.patch.object(build_backend.venv, "EnvBuilder") as environment, \
                        mock.patch.object(build_backend.subprocess, "run") as run, \
                        redirect_stderr(errors), self.assertRaises(SystemExit) as caught:
                    build_backend.main()
                self.assertEqual(caught.exception.code, 2)
                self.assertIn("Python and Node.js must use the same architecture", errors.getvalue())
                environment.assert_not_called()
                run.assert_not_called()
                self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
