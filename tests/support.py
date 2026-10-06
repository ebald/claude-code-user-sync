"""Portable helpers for synthetic fixtures; no live Claude data is accessed."""
import errno
import os
from pathlib import Path
import stat

from asset_audit import is_link


def create_symlink(test, link, target, *, directory=False):
    try:
        Path(link).symlink_to(target, target_is_directory=directory)
        if os.name == "nt" and not is_link(Path(link)):
            # Some compatibility runtimes create a host link without exposing
            # Windows reparse metadata. That cannot exercise Windows safety.
            if directory:
                Path(link).rmdir()
            else:
                Path(link).unlink()
            test.skipTest("The runtime does not expose symbolic links as Windows reparse points")
    except NotImplementedError:
        test.skipTest("This platform does not support symbolic links")
    except OSError as error:
        unsupported = error.errno in (errno.ENOSYS, errno.ENOTSUP)
        no_windows_privilege = os.name == "nt" and getattr(error, "winerror", None) == 1314
        if unsupported or no_windows_privilege:
            test.skipTest("Symbolic links require Windows Developer Mode or the symlink privilege")
        raise


def assert_private_mode(test, path, expected):
    path = Path(path)
    if os.name != "nt":
        test.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)
    else:
        # ACLs, inherited from the chosen private backup directory, replace
        # Unix permission bits. Still require an ordinary local file/directory.
        test.assertFalse(is_link(path))
        test.assertTrue(path.is_dir() if expected == 0o700 else path.is_file())
