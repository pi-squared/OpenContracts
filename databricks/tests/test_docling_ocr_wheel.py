"""Verify the actual dependency wheel; no OCR implementation bytes may change."""

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_docling_ocr import build


@unittest.skipUnless(
    os.environ.get("DOCLING_OCR_STOCK_WHEEL"), "Requires retained stock RapidOCR wheel"
)
class HeadlessOCRWheelTests(unittest.TestCase):
    def test_only_distribution_metadata_changes(self):
        stock = Path(os.environ["DOCLING_OCR_STOCK_WHEEL"])
        with tempfile.TemporaryDirectory() as temporary:
            wheel = build(stock, Path(temporary) / "built")
            with zipfile.ZipFile(stock) as original, zipfile.ZipFile(wheel) as patched:
                before = {
                    name: original.read(name)
                    for name in original.namelist()
                    if name.startswith("rapidocr/") and not name.endswith("/")
                }
                after = {
                    name: patched.read(name)
                    for name in patched.namelist()
                    if name.startswith("rapidocr/") and not name.endswith("/")
                }
                self.assertEqual(before, after)
                metadata = patched.read("rapidocr-3.9.2+oc39.1.dist-info/METADATA")
                self.assertIn(
                    b"Requires-Dist: opencv-python-headless==4.12.0.88", metadata
                )
                self.assertNotIn(b"Requires-Dist: opencv_python", metadata)
                self.assertTrue(patched.testzip() is None)

    def test_changed_stock_wheel_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "changed.whl"
            source.write_bytes(b"not the retained source")
            with self.assertRaisesRegex(ValueError, "pinned stock source"):
                build(source, Path(temporary) / "rejected")
            self.assertFalse((Path(temporary) / "rejected").exists())
