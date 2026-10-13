"""Check release packaging through its public staging boundary and archive."""

import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

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
            self.port / "port/runtime/staged_dependencies.py",
            (PORT_ROOT / "port/runtime/staged_dependencies.py").read_bytes(),
        )
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

    def assemble_declared_runtime_overlays(self):
        real_lock = json.loads((PORT_ROOT / "upstream.lock.json").read_text())
        fixture_lock_path = self.port / "upstream.lock.json"
        fixture_lock = json.loads(fixture_lock_path.read_text())
        for overlay in real_lock["overlays"]:
            if (
                overlay["target"].startswith("databricks_port/")
                or overlay["source"] == "tools/database_privileges.py"
            ):
                content = (PORT_ROOT / overlay["source"]).read_bytes()
                self.write(self.port / overlay["source"], content)
                self.write(self.source / overlay["target"], content)
                fixture_lock["overlays"].append(overlay)
        fixture_lock_path.write_text(json.dumps(fixture_lock))

    def oversized_parser_inputs(self):
        """Supply valid pinned wheels with an unchanged model exceeding upload limits."""
        model = random.Random(126).randbytes(11 * 1024 * 1024)
        self.write(self.root / "nltk/english", b"Frozen fixture language data\n")
        wheel_format = "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        inputs = {}
        for name, version in (
            ("warp_ingest", "2.1.0"),
            ("rapidocr_onnxruntime", "1.4.4"),
        ):
            wheel_path = self.root / f"{name}-{version}-py3-none-any.whl"
            with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as wheel:
                wheel.writestr(name + "/__init__.py", b"# fixture package\n")
                if name == "rapidocr_onnxruntime":
                    wheel.writestr(name + "/model.onnx", model)
                metadata = f"Metadata-Version: 2.1\nName: {name.replace('_', '-')}\nVersion: {version}\n"
                if name == "rapidocr_onnxruntime":
                    metadata += "Requires-Dist: opencv-python>=4.5.1.48\n"
                wheel.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
                wheel.writestr(f"{name}-{version}.dist-info/WHEEL", wheel_format)
                wheel.writestr(f"{name}-{version}.dist-info/RECORD", "")
            inputs[name] = wheel_path
        warp = inputs["warp_ingest"]
        ocr = inputs["rapidocr_onnxruntime"]
        lock = {
            "distribution": "warp-ingest",
            "upstream_version": "2.1.0",
            "version": "2.1.0+oc39.1",
            "wheel_filename": warp.name,
            "wheel_sha256": self.sha(warp.read_bytes()),
            "patches": [],
            "stock_files": {
                "warp_ingest/__init__.py": self.sha(b"# fixture package\n")
            },
            "patched_files": {},
            "nltk_assets": {"english": self.sha(b"Frozen fixture language data\n")},
            "rapidocr": {
                "upstream_version": "1.4.4",
                "version": "1.4.4+oc39.1",
                "wheel_filename": ocr.name,
                "wheel_sha256": self.sha(ocr.read_bytes()),
                "stock_requirement": "Requires-Dist: opencv-python>=4.5.1.48\n",
                "headless_requirement": "Requires-Dist: opencv-python-headless==5.0.0.93\n",
            },
        }
        self.write(
            self.port / "port/dependencies/warp/lock.json", json.dumps(lock).encode()
        )
        self.write(
            self.port / "port/runtime/launch.py",
            (PORT_ROOT / "port/runtime/launch.py").read_bytes(),
        )
        app = b"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
from importlib import metadata
import rapidocr_onnxruntime, warp_ingest
runtime = Path.cwd()
assert Path(rapidocr_onnxruntime.__file__).parent.parent == runtime
assert Path(warp_ingest.__file__).parent.parent == runtime
assert metadata.version('rapidocr-onnxruntime') == '1.4.4+oc39.1'
assert metadata.version('warp-ingest') == '2.1.0+oc39.1'
with tempfile.TemporaryDirectory() as worker:
    result = subprocess.check_output([sys.executable, '-c',
        "import rapidocr_onnxruntime,sys;from pathlib import Path;"
        "assert Path(rapidocr_onnxruntime.__file__).parent.parent==Path(sys.argv[1]);"
        "print('worker-from-runtime')",
        str(runtime)], cwd=worker, env={**os.environ, 'PYTHONPATH': str(runtime)}, text=True)
assert result.strip() == 'worker-from-runtime'
model_hash = hashlib.sha256((runtime / 'rapidocr_onnxruntime/model.onnx').read_bytes()).hexdigest()
print(json.dumps({'model_sha256': model_hash,
                  'interpreter': sys.executable, 'offline_imports': 2, 'worker': result.strip()}))
"""
        self.write(self.source / "app.py", app)
        source_lock_path = self.port / "upstream.lock.json"
        source_lock = json.loads(source_lock_path.read_text())
        source_lock["patched_files"]["app.py"] = self.sha(app)
        source_lock_path.write_text(json.dumps(source_lock))
        return warp, ocr, model

    def test_oversized_vendor_is_self_contained_and_installed_offline_in_ephemeral_runtime(
        self,
    ):
        warp, ocr, model = self.oversized_parser_inputs()
        self.assertGreater(ocr.stat().st_size, 10 * 1024 * 1024)
        with redirect_stdout(io.StringIO()):
            stage_app.stage(
                self.source,
                self.destination,
                "https://fixture.example.invalid",
                warp_wheel=warp,
                warp_nltk_data=self.root / "nltk",
                rapidocr_wheel=ocr,
            )
        oversized = [
            str(path.relative_to(self.destination))
            for path in self.destination.rglob("*")
            if path.is_file() and path.stat().st_size > 10 * 1024 * 1024
        ]
        self.assertEqual(
            oversized,
            [],
            "Every uploaded file must remain below the unchanged Git App limit",
        )
        self.assertNotIn(
            "./vendor/", (self.destination / "requirements.txt").read_text()
        )
        owned_venv = self.root / "launcher-venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(owned_venv)],
            check=True,
            capture_output=True,
            text=True,
        )
        owned_python = owned_venv / "bin/python"
        environment = {**os.environ, "PYTHONPATH": "", "PIP_NO_INDEX": "1"}
        before = {
            str(path.relative_to(self.destination)): self.sha(path.read_bytes())
            for path in self.destination.rglob("*")
            if path.is_file()
        }
        result = subprocess.run(
            [str(owned_python), str(self.destination / "app.py")],
            cwd=self.destination,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        print(
            json.dumps(
                {
                    "offline_launcher_process": {
                        "argv": result.args,
                        "cwd": str(self.destination),
                        "actual_exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                }
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {
            str(path.relative_to(self.destination)): self.sha(path.read_bytes())
            for path in self.destination.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            after, before, "Starting the app preserves the staged release bytes"
        )
        observed = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(observed["model_sha256"], self.sha(model))
        self.assertEqual(observed["offline_imports"], 2)
        self.assertEqual(observed["worker"], "worker-from-runtime")
        self.assertEqual(observed["interpreter"], str(owned_python))

    def test_changed_vendor_digest_and_archive_part_refuse_before_install_or_startup(
        self,
    ):
        warp, ocr, _ = self.oversized_parser_inputs()
        for fault in ("vendor", "part"):
            with self.subTest(fault=fault):
                release = self.root / ("release-" + fault)
                with redirect_stdout(io.StringIO()):
                    stage_app.stage(
                        self.source,
                        release,
                        "https://fixture.example.invalid",
                        warp_wheel=warp,
                        warp_nltk_data=self.root / "nltk",
                        rapidocr_wheel=ocr,
                    )
                manifest_path = release / "release.json"
                manifest = json.loads(manifest_path.read_text())
                if fault == "vendor":
                    manifest["warp_runtime"]["rapidocr"]["wheel_sha256"] = "0" * 64
                    manifest_path.write_text(json.dumps(manifest))
                    message = "Vendor wheel checksum mismatch"
                else:
                    part = release / manifest["parts"][0]["name"]
                    part.write_bytes(part.read_bytes() + b"changed")
                    message = "Release part checksum mismatch"
                result = subprocess.run(
                    [sys.executable, str(release / "app.py")],
                    cwd=release,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("Successfully installed", result.stdout)
                self.assertNotIn("offline_imports", result.stdout)

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

    def test_git_release_references_configuration_without_publishing_installation_values(
        self,
    ):
        self.write(
            self.port / "tools/installation_configuration.py",
            b"# fixture configuration contract\n",
        )
        self.write(
            self.port / "port/runtime/app.yaml",
            b"command: [python, app.py]\nenv:\n  - name: OPENCONTRACTS_SCHEMA\n    value: opencontracts\n",
        )
        with redirect_stdout(io.StringIO()):
            stage_app.stage(
                self.source,
                self.destination,
                "https://private-installation.invalid",
                "/Volumes/private/catalog/definitions/workflow-packages",
                configuration_resource="installation-config",
            )
        config = yaml.safe_load((self.destination / "app.yaml").read_text())
        self.assertIn(
            {"name": "INSTALLATION_CONFIG_JSON", "valueFrom": "installation-config"},
            config["env"],
        )
        self.assertFalse(
            any(
                item["name"]
                in ("APP_ORIGIN", "WORKFLOW_PACKAGE_ROOT", "OPENCONTRACTS_SCHEMA")
                for item in config["env"]
            )
        )
        self.assertNotIn(
            "private-installation", (self.destination / "app.yaml").read_text()
        )
        self.assertTrue((self.destination / "installation_configuration.py").is_file())

    def test_declared_release_files_import_the_warp_boundary_in_an_isolated_process(
        self,
    ):
        # Package the actual declared Python overlays through the public stage
        # interface. Neither the checkout nor port/python is on the import path.
        self.assemble_declared_runtime_overlays()
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

    def test_declared_release_imports_existing_startup_with_its_staged_privilege_policy(
        self,
    ):
        self.assemble_declared_runtime_overlays()
        self.stage()
        release = json.loads((self.destination / "release.json").read_text())
        archive_bytes = b"".join(
            (self.destination / part["name"]).read_bytes() for part in release["parts"]
        )
        self.assertEqual(self.sha(archive_bytes), release["archive_sha256"])
        runtime = self.root / "isolated-runtime"
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            archive.extractall(runtime)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                """
import json, sys
from pathlib import Path
runtime = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(runtime))
from databricks_port import lakebase, startup, database_privileges
origins = {module.__name__: str(Path(module.__file__).resolve())
           for module in (lakebase, startup, database_privileges)}
assert all(Path(origin).is_relative_to(runtime) for origin in origins.values())
assert Path(database_privileges.__file__).resolve() == runtime / 'databricks_port/database_privileges.py'
assert callable(startup.initialize)
assert callable(lakebase.bootstrap)
print(json.dumps({'imports': 3, 'origins': origins}))
""",
                str(runtime),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )
        print(
            json.dumps(
                {
                    "archive_import_process": {
                        "argv": result.args,
                        "cwd": str(self.root),
                        "actual_exit_code": result.returncode,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    }
                }
            )
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        observed = json.loads(result.stdout)
        self.assertEqual(observed["imports"], 3)
        self.assertEqual(
            observed["origins"]["databricks_port.database_privileges"],
            str(runtime / "databricks_port/database_privileges.py"),
        )
