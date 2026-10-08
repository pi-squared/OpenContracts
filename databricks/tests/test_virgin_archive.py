"""A fresh release excludes tracked fixture data as well as untracked input."""

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import stage_app


class VirginArchiveTests(unittest.TestCase):
    def test_tracked_inputs_and_nested_fixtures_are_excluded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, recipe, release = (
                root / name for name in ("source", "recipe", "release")
            )
            files = {
                "LICENSE": "fixture",
                "app.py": "pass",
                "frontend/dist/index.html": "<html></html>",
                "opencontractserver/ordinary.py": "value = 1",
                "fixtures/recorded.json": '{"result":"old"}',
                "opencontractserver/fixtures/recorded.json": '{"result":"old"}',
                "opencontractserver/cassettes/request.json": '{"result":"old"}',
                "opencontractserver/input.pdf": "fixture",
                "opencontractserver/result.csv": "fixture",
                "opencontractserver/db.sqlite3": "fixture",
            }
            for name, content in files.items():
                p = source / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            for name, content in {
                "upstream.lock.json": "{}",
                "port/runtime/requirements.lock": "",
                "port/runtime/launch.py": "pass",
                "port/runtime/app.yaml": "env: []",
            }.items():
                p = recipe / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            lock = {"commit": "fixture", "overlays": [], "patched_files": {}}
            with patch.object(stage_app, "ROOT", recipe), patch.object(
                stage_app, "verify_prepared", return_value=(lock, set(files))
            ), redirect_stdout(io.StringIO()):
                stage_app.stage(source, release, "https://fixture.invalid")
            manifest = json.loads((release / "release.json").read_text())
            archive = b"".join(
                (release / part["name"]).read_bytes() for part in manifest["parts"]
            )
            with zipfile.ZipFile(io.BytesIO(archive)) as payload:
                self.assertIn("opencontractserver/ordinary.py", payload.namelist())
                self.assertFalse(
                    any(
                        "fixtures" in name
                        or "cassettes" in name
                        or name.endswith((".pdf", ".csv", ".sqlite3"))
                        for name in payload.namelist()
                    )
                )
