import base64
import hashlib
from pathlib import Path
import tempfile
import unittest

from asset_audit import recover_preserved_outputs


class PreviewCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.original = self.base / "missing-original.png"
        self.image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=")
        self.preview = self.base / "read-result.png"
        self.preview.write_bytes(self.image)
        self.prior = {"entries": [{"path": str(self.original), "status": "missing", "scope": "output",
            "saved_read_preview": {"output_path": str(self.preview), "sha256": hashlib.sha256(self.image).hexdigest(),
                                   "media_type": "image/png", "reason": "saved_read_preview"}}]}

    def report(self):
        return {"summary": {"missing_output_files": 1, "prepared_output_files": 0},
                "entries": [{"path": str(self.original), "kind": "image", "status": "missing", "scope": "output"}]}

    def test_preview_cache_survives_runs_without_claiming_original_recovery(self):
        first = recover_preserved_outputs(self.report(), [self.prior], self.base / "first")
        preview = first["entries"][0]["saved_read_preview"]
        self.assertEqual(Path(preview["output_path"]).read_bytes(), self.image)
        self.assertEqual(Path(preview["output_path"]).name, "missing-original.preview.png")
        self.assertEqual(first["summary"]["saved_read_images"], 1)
        self.assertEqual(first["summary"]["preserved_output_files"], 0)
        self.assertEqual(first["summary"]["unpreserved_output_files"], 1)
        self.preview.unlink()
        second = recover_preserved_outputs(self.report(), [first], self.base / "second")
        self.assertEqual(Path(second["entries"][0]["saved_read_preview"]["output_path"]).read_bytes(), self.image)
        self.assertFalse(self.original.exists())

    def test_mismatched_preview_hash_is_not_published(self):
        self.preview.write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            recover_preserved_outputs(self.report(), [self.prior], self.base / "failed")
        self.assertFalse(any((self.base / "failed/assets").glob("*")))
        self.assertFalse(self.original.exists())


if __name__ == "__main__":
    unittest.main()
