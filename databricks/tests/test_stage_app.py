"""Check release packaging through its public staging boundary and archive."""

import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import stage_app

PORT_ROOT = Path(__file__).resolve().parents[1]


class StageAppTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        self.root = Path(self.storage.name)
        self.source = self.root / "source"
        self.port = self.root / "port"
        self.destination = self.root / "release"
        self.source.mkdir()
        stock = {
            "LICENSE": b"Fixture license\n",
            "protected.py": b"protected = True\n",
            "opencontractserver/current.py": b"value = 'before'\n",
            "opencontractserver/ordinary.py": b"ordinary = True\n",
            "app.py": b"pass\n",
        }
        for name, content in stock.items():
            self.write(self.source / name, content)
        subprocess.run(["git", "init", "-q", str(self.source)], check=True)
        subprocess.run(["git", "add", "--", *stock], cwd=self.source, check=True)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "Fixture upstream",
            ],
            cwd=self.source,
            check=True,
        )
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.source, text=True
        ).strip()
        self.overlay_before = b"overlay = 'before'\n"
        self.overlay_after = b"overlay = 'patched'\n"
        patched = {
            "opencontractserver/current.py": b"value = 'after'\n",
            "databricks_port/projected.py": self.overlay_after,
            "opencontractserver/added.py": b"added = True\n",
        }
        for name, content in patched.items():
            self.write(self.source / name, content)
        self.write(
            self.source / "frontend/dist/index.html", b"Fixture production frontend\n"
        )
        self.write(self.source / "private-input.pdf", b"Must stay out of release\n")
        lock = {
            "commit": revision,
            "license_sha256": self.sha(stock["LICENSE"]),
            "unchanged_stock_files": {"protected.py": self.sha(stock["protected.py"])},
            "overlays": [
                {
                    "source": "port/projected.py",
                    "target": "databricks_port/projected.py",
                    "sha256": self.sha(self.overlay_before),
                }
            ],
            "patched_files": {
                name: self.sha(content) for name, content in patched.items()
            },
        }
        self.write(self.port / "upstream.lock.json", json.dumps(lock).encode())
        self.write(self.port / "port/projected.py", self.overlay_before)
        self.write(self.port / "port/runtime/requirements.lock", b"Django==5.2\n")
        self.write(self.port / "port/runtime/launch.py", b"pass\n")
        self.write(
            self.port / "port/runtime/app.yaml", b"command: [python, app.py]\nenv: []\n"
        )
        configuration = patch.object(stage_app, "ROOT", self.port)
        configuration.start()
        self.addCleanup(configuration.stop)

    @staticmethod
    def sha(content):
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def stage(self):
        with redirect_stdout(io.StringIO()):
            stage_app.stage(
                self.source, self.destination, "https://fixture.example.invalid"
            )

    def test_patched_overlay_and_new_patch_file_are_hash_checked_and_packaged(self):
        self.stage()
        release = json.loads((self.destination / "release.json").read_text())
        archive = b"".join(
            (self.destination / part["name"]).read_bytes() for part in release["parts"]
        )
        self.assertEqual(self.sha(archive), release["archive_sha256"])
        with zipfile.ZipFile(io.BytesIO(archive)) as payload:
            self.assertEqual(
                payload.read("databricks_port/projected.py"), self.overlay_after
            )
            self.assertEqual(
                payload.read("opencontractserver/added.py"), b"added = True\n"
            )
            self.assertNotIn("private-input.pdf", payload.namelist())
        self.assertFalse(release["contains_domain_inputs"])

    def test_reverting_a_patched_overlay_to_its_baseline_is_rejected(self):
        self.write(self.source / "databricks_port/projected.py", self.overlay_before)
        with self.assertRaisesRegex(ValueError, "Prepared overlay differs"):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_an_undeclared_stock_modification_is_rejected_before_packaging(self):
        self.write(
            self.source / "opencontractserver/ordinary.py", b"ordinary = False\n"
        )
        with self.assertRaisesRegex(
            ValueError, "Prepared tracked modifications differ"
        ):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_parser_dependencies_need_explicit_verified_inputs_before_packaging(self):
        self.write(self.port / "port/dependencies/warp/lock.json", b"{}\n")
        with self.assertRaisesRegex(
            ValueError, "requires --warp-wheel.*--rapidocr-wheel"
        ):
            self.stage()
        self.assertFalse(self.destination.exists())

    def test_declared_release_files_import_the_warp_boundary_in_an_isolated_process(
        self,
    ):
        # Package the actual declared Python overlays through the public stage
        # interface. Neither the checkout nor port/python is on the import path.
        real_lock = json.loads((PORT_ROOT / "upstream.lock.json").read_text())
        fixture_lock_path = self.port / "upstream.lock.json"
        fixture_lock = json.loads(fixture_lock_path.read_text())
        for overlay in real_lock["overlays"]:
            if overlay["target"].startswith("databricks_port/"):
                content = (PORT_ROOT / overlay["source"]).read_bytes()
                self.write(self.port / overlay["source"], content)
                self.write(self.source / overlay["target"], content)
                fixture_lock["overlays"].append(overlay)
        fixture_lock_path.write_text(json.dumps(fixture_lock))
        self.stage()
        release = json.loads((self.destination / "release.json").read_text())
        archive = self.root / "staged-source.zip"
        archive.write_bytes(
            b"".join(
                (self.destination / part["name"]).read_bytes()
                for part in release["parts"]
            )
        )
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                """
import json, sys
sys.path.insert(0, sys.argv[1])
from databricks_port import warp_pdf, parser_exports
assert callable(warp_pdf.parse_warp_pdf)
assert callable(parser_exports.warp_export)
assert all(module.__file__.startswith(sys.argv[1] + '/')
           for module in (warp_pdf, parser_exports))
print(json.dumps({'parser_version': warp_pdf.VERSION, 'assembled_imports': 2}))
""",
                str(archive),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"parser_version": "2.1.0+oc39.1", "assembled_imports": 2},
        )
