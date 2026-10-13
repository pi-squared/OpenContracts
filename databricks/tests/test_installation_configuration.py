"""Git runtime consumes bound configuration before starting the application."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BoundConfigurationTests(unittest.TestCase):
    def test_launcher_uses_bound_origin_schema_and_package_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            archive = directory / "opencontracts.part000"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(
                    "app.py",
                    "import json,os\n"
                    "print(json.dumps({k:os.environ.get(k) for k in "
                    "['APP_ORIGIN','OPENCONTRACTS_SCHEMA','WORKFLOW_INSTALL_HASHES',"
                    "'OPENCONTRACTS_DATABASE_MODE']}))\n",
                )
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            installer = (ROOT / "port/runtime/staged_dependencies.py").read_bytes()
            (directory / "staged_dependencies.py").write_bytes(installer)
            (directory / "release.json").write_text(
                json.dumps(
                    {
                        "parts": [{"name": archive.name, "sha256": digest}],
                        "archive_sha256": digest,
                        "dependency_installer_sha256": hashlib.sha256(
                            installer
                        ).hexdigest(),
                    }
                )
            )
            (directory / "app.py").write_bytes(
                (ROOT / "port/runtime/launch.py").read_bytes()
            )
            module = ROOT / "tools/installation_configuration.py"
            if module.exists():
                (directory / module.name).write_bytes(module.read_bytes())
            config = {
                "APP_ORIGIN": "https://bound.invalid",
                "OPENCONTRACTS_SCHEMA": "retained",
                "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/workflow-packages",
                "WORKFLOW_INSTALL_HASHES": '["' + "a" * 64 + '"]',
                "PILOT_USERNAME": "pilot-owner",
                "OPENCONTRACTS_DATABASE_MODE": "existing",
            }
            process = subprocess.run(
                [sys.executable, str(directory / "app.py")],
                env={**os.environ, "INSTALLATION_CONFIG_JSON": json.dumps(config)},
                capture_output=True,
                text=True,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            observed = json.loads(process.stdout)
            self.assertEqual(observed["APP_ORIGIN"], "https://bound.invalid")
            self.assertEqual(observed["OPENCONTRACTS_SCHEMA"], "retained")
            self.assertEqual(observed["OPENCONTRACTS_DATABASE_MODE"], "existing")
            self.assertEqual(
                observed["WORKFLOW_INSTALL_HASHES"], config["WORKFLOW_INSTALL_HASHES"]
            )

    def test_bound_configuration_rejects_credential_overrides_before_startup(self):
        process = subprocess.run(
            [sys.executable, str(ROOT / "port/runtime/launch.py")],
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "tools"),
                "INSTALLATION_CONFIG_JSON": json.dumps(
                    {"DATABRICKS_CLIENT_SECRET": "fixture-forbidden"}
                ),
            },
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("unsupported settings", process.stderr)
        self.assertNotIn("fixture-forbidden", process.stderr)

    def test_launcher_rejects_unknown_database_mode_before_application_startup(self):
        configuration = {
            "APP_ORIGIN": "https://bound.invalid",
            "OPENCONTRACTS_SCHEMA": "retained",
            "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/packages",
            "WORKFLOW_INSTALL_HASHES": "[]",
            "PILOT_USERNAME": "pilot",
            "OPENCONTRACTS_DATABASE_MODE": "skip-migrations",
        }
        process = subprocess.run(
            [sys.executable, str(ROOT / "port/runtime/launch.py")],
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "tools"),
                "INSTALLATION_CONFIG_JSON": json.dumps(configuration),
            },
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("database mode must be owned or existing", process.stderr)


if __name__ == "__main__":
    unittest.main()
