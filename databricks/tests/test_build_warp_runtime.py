"""Check deterministic dependency assembly and rejection through its interface."""

import base64
import csv
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.build_warp_runtime import build


class WarpRuntimeBuildTests(unittest.TestCase):
    def setUp(self):
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.root = Path(storage.name)
        self.wheel = self.root / "warp_ingest-2.1.0-py3-none-any.whl"
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "english").write_bytes(b"Frozen fixture language data\n")
        stock = b"column_safe = False\n"
        patched = b"column_safe = True\n"
        with zipfile.ZipFile(self.wheel, "w") as wheel:
            wheel.writestr("warp_ingest/parser.py", stock)
            wheel.writestr(
                "warp_ingest-2.1.0.dist-info/METADATA",
                "Name: warp-ingest\nVersion: 2.1.0\n",
            )
            wheel.writestr("warp_ingest-2.1.0.dist-info/RECORD", "")
        dependency = self.root / "port/dependencies/warp"
        dependency.mkdir(parents=True)
        patch = b"--- a/warp_ingest/parser.py\n+++ b/warp_ingest/parser.py\n@@ -1 +1 @@\n-column_safe = False\n+column_safe = True\n"  # noqa: E501
        (dependency / "columns.patch").write_bytes(patch)

        def sha(value):
            return hashlib.sha256(value).hexdigest()

        lock = {
            "distribution": "warp-ingest",
            "upstream_version": "2.1.0",
            "version": "2.1.0+oc39.1",
            "wheel_filename": self.wheel.name,
            "wheel_sha256": sha(self.wheel.read_bytes()),
            "patches": [
                {"path": "port/dependencies/warp/columns.patch", "sha256": sha(patch)}
            ],
            "stock_files": {"warp_ingest/parser.py": sha(stock)},
            "patched_files": {"warp_ingest/parser.py": sha(patched)},
            "nltk_assets": {"english": sha((self.assets / "english").read_bytes())},
        }
        (dependency / "lock.json").write_text(json.dumps(lock))
        self.ocr_wheel = self.root / "rapidocr_onnxruntime-1.4.4-py3-none-any.whl"
        with zipfile.ZipFile(self.ocr_wheel, "w") as wheel:
            wheel.writestr("rapidocr_onnxruntime/ocr.py", "pass\n")
            wheel.writestr(
                "rapidocr_onnxruntime/model.onnx", b"Unchanged fixture model weights\n"
            )
            wheel.writestr(
                "rapidocr_onnxruntime-1.4.4.dist-info/METADATA",
                "Name: rapidocr-onnxruntime\nVersion: 1.4.4\nRequires-Dist: opencv-python>=4.5.1.48\n",
            )
            wheel.writestr("rapidocr_onnxruntime-1.4.4.dist-info/RECORD", "")

    def add_ocr_lock(self):
        path = self.root / "port/dependencies/warp/lock.json"
        lock = json.loads(path.read_text())
        lock["rapidocr"] = {
            "upstream_version": "1.4.4",
            "version": "1.4.4+oc39.1",
            "wheel_filename": self.ocr_wheel.name,
            "wheel_sha256": hashlib.sha256(self.ocr_wheel.read_bytes()).hexdigest(),
            "stock_requirement": "Requires-Dist: opencv-python>=4.5.1.48\n",
            "headless_requirement": "Requires-Dist: opencv-python-headless==5.0.0.93\n",
        }
        path.write_text(json.dumps(lock))

    def test_patched_wheel_is_reproducible_and_installation_records_verify_every_byte(
        self,
    ):
        first = build(self.wheel, self.assets, self.root / "first", root=self.root)
        second = build(self.wheel, self.assets, self.root / "second", root=self.root)
        self.assertEqual(first, second)
        with zipfile.ZipFile(self.root / "first" / first["wheel_filename"]) as wheel:
            self.assertEqual(
                wheel.read("warp_ingest/parser.py"), b"column_safe = True\n"
            )
            self.assertIn(
                b"Version: 2.1.0+oc39.1\n",
                wheel.read("warp_ingest-2.1.0+oc39.1.dist-info/METADATA"),
            )
            record = wheel.read("warp_ingest-2.1.0+oc39.1.dist-info/RECORD").decode()
            for name, checksum, size in csv.reader(io.StringIO(record)):
                if checksum:
                    content = wheel.read(name)
                    expected = (
                        base64.urlsafe_b64encode(hashlib.sha256(content).digest())
                        .decode()
                        .rstrip("=")
                    )
                    self.assertEqual(checksum, "sha256=" + expected)
                    self.assertEqual(int(size), len(content))

    def test_changed_stock_wheel_is_refused_before_any_bundle_is_written(self):
        self.wheel.write_bytes(self.wheel.read_bytes() + b"changed")
        destination = self.root / "refused"
        with self.assertRaisesRegex(ValueError, "pinned stock distribution"):
            build(self.wheel, self.assets, destination, root=self.root)
        self.assertFalse(destination.exists())

    def test_changed_frozen_language_data_is_refused_before_any_bundle_is_written(self):
        (self.assets / "english").write_bytes(b"changed")
        destination = self.root / "refused"
        with self.assertRaisesRegex(ValueError, "NLTK asset differs"):
            build(self.wheel, self.assets, destination, root=self.root)
        self.assertFalse(destination.exists())

    def test_headless_dependency_substitution_preserves_ocr_code_and_model_bytes(self):
        self.add_ocr_lock()
        first = build(
            self.wheel,
            self.assets,
            self.root / "first",
            root=self.root,
            rapidocr_wheel=self.ocr_wheel,
        )
        second = build(
            self.wheel,
            self.assets,
            self.root / "second",
            root=self.root,
            rapidocr_wheel=self.ocr_wheel,
        )
        self.assertEqual(first, second)
        with zipfile.ZipFile(
            self.root / "first" / first["rapidocr"]["wheel_filename"]
        ) as wheel:
            metadata = wheel.read(
                "rapidocr_onnxruntime-1.4.4+oc39.1.dist-info/METADATA"
            )
            self.assertIn(
                b"Requires-Dist: opencv-python-headless==5.0.0.93\n", metadata
            )
            self.assertNotIn(b"Requires-Dist: opencv-python>=", metadata)
            self.assertEqual(
                wheel.read("rapidocr_onnxruntime/model.onnx"),
                b"Unchanged fixture model weights\n",
            )
            self.assertEqual(wheel.read("rapidocr_onnxruntime/ocr.py"), b"pass\n")

    def test_changed_ocr_wheel_is_refused_before_any_bundle_is_written(self):
        self.add_ocr_lock()
        self.ocr_wheel.write_bytes(self.ocr_wheel.read_bytes() + b"changed")
        destination = self.root / "refused"
        with self.assertRaisesRegex(ValueError, "RapidOCR wheel differs"):
            build(
                self.wheel,
                self.assets,
                destination,
                root=self.root,
                rapidocr_wheel=self.ocr_wheel,
            )
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
