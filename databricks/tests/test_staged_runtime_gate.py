"""Verify the deployment gate through its supported command-line boundary."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "tools/verify_staged_runtime.py"


class StagedRuntimeGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.release = self.root / "release"
        self.receipt = self.root / "verification.json"

    def invoke(self, *extra):
        return subprocess.run(
            [
                sys.executable,
                str(COMMAND),
                "--release",
                str(self.release),
                "--python",
                sys.executable,
                "--output",
                str(self.receipt),
                *extra,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_missing_release_stops_verification_with_an_actionable_private_receipt(
        self,
    ):
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.receipt.is_file(), result.stderr)
        report = json.loads(self.receipt.read_text())
        self.assertFalse(report["passed"])
        self.assertEqual(report["reason"], "release_missing")
        self.assertEqual(report["executed"], 0)
        self.assertEqual(report["skipped"], 0)

    def test_missing_runtime_inputs_stop_before_the_required_smoke(self):
        self.release.mkdir()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        report = json.loads(self.receipt.read_text())
        self.assertEqual(report["reason"], "release_inputs_missing")
        self.assertEqual(report["executed"], 0)

    def test_unverified_receipt_prevents_the_following_workspace_command(self):
        for previous in (
            None,
            {"passed": False},
            {"passed": True, "executed": 0},
            {"passed": True, "executed": 1, "skipped": 1},
        ):
            with self.subTest(previous=previous):
                if self.receipt.exists():
                    self.receipt.unlink()
                baseline = self.root / "baseline.json"
                if previous is not None:
                    baseline.write_text(json.dumps(previous))
                marker = self.root / "workspace-command-ran"
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        'set -e\nmarker="$1"\nshift\n"$@"\ntouch "$marker"',
                        "guarded-deployment",
                        str(marker),
                        sys.executable,
                        str(COMMAND),
                        "--release",
                        str(self.release),
                        "--python",
                        sys.executable,
                        "--receipt",
                        str(baseline),
                        "--output",
                        str(self.receipt),
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())
                report = json.loads(self.receipt.read_text())
                self.assertFalse(report["passed"])
                self.assertEqual(
                    report["reason"],
                    "receipt_missing" if previous is None else "receipt_not_verified",
                )


@unittest.skipUnless(
    os.environ.get("WARP_TEST_STAGED_RELEASE")
    and os.environ.get("WARP_GATE_TEST_PYTHON"),
    "needs an assembled release and isolated Warp gate interpreter",
)
class StagedRuntimeRealReleaseTests(unittest.TestCase):
    def run_gate(self, release, output, *extra, command=COMMAND):
        return subprocess.run(
            [
                sys.executable,
                str(command),
                "--release",
                str(release),
                "--python",
                os.environ["WARP_GATE_TEST_PYTHON"],
                "--output",
                str(output),
                *extra,
            ],
            cwd=output.parent,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )

    @unittest.skipUnless(
        sys.platform == "linux",
        "needs Linux file notification for concurrent writer control",
    )
    def test_receipt_read_failure_cannot_retain_an_earlier_success(self):
        import ctypes
        import threading

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            release = Path(os.environ["WARP_TEST_STAGED_RELEASE"])
            baseline = directory / "baseline.json"
            self.assertEqual(self.run_gate(release, baseline).returncode, 0)
            library = ctypes.CDLL(None, use_errno=True)
            descriptor = library.inotify_init1(os.O_CLOEXEC)
            self.assertGreaterEqual(descriptor, 0)
            try:
                self.assertGreaterEqual(
                    library.inotify_add_watch(descriptor, os.fsencode(baseline), 0x10),
                    0,
                )

                def concurrent_writer():
                    os.read(
                        descriptor, 4096
                    )  # IN_CLOSE_NOWRITE: first receipt read completed.
                    baseline.unlink()

                writer = threading.Thread(target=concurrent_writer, daemon=True)
                writer.start()
                output = directory / "revalidated.json"
                result = self.run_gate(release, output, "--receipt", str(baseline))
                writer.join(timeout=5)
                self.assertFalse(writer.is_alive())
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(json.loads(output.read_text())["passed"])
            finally:
                os.close(descriptor)

    def test_receipt_admits_unchanged_release_and_stops_after_a_staged_file_changes(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            release = directory / "release"
            shutil.copytree(os.environ["WARP_TEST_STAGED_RELEASE"], release)
            baseline = directory / "baseline.json"
            self.assertEqual(self.run_gate(release, baseline).returncode, 0)
            unchanged = directory / "unchanged.json"
            result = self.run_gate(release, unchanged, "--receipt", str(baseline))
            self.assertEqual(result.returncode, 0, result.stderr)
            with (release / "app.py").open("a") as target:
                target.write("\n# changed after verification\n")
            changed = directory / "changed.json"
            result = self.run_gate(release, changed, "--receipt", str(baseline))
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(changed.read_text())
            self.assertFalse(report["passed"])
            self.assertEqual(report["reason"], "staged_files_changed")

    def test_old_launcher_and_missing_declared_import_cannot_be_deployed(self):
        for fault in ("old_launcher", "missing_import"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                release = directory / "release"
                shutil.copytree(os.environ["WARP_TEST_STAGED_RELEASE"], release)
                if fault == "old_launcher":
                    (release / "app.py").write_text(
                        "import os, subprocess, sys\nos.chdir('/tmp')\nsubprocess.run([sys.executable, 'app.py'])\n"
                    )
                    expected = "launcher_source_mismatch"
                else:
                    import hashlib

                    manifest = json.loads((release / "release.json").read_text())
                    original = directory / "original.zip"
                    original.write_bytes(
                        b"".join(
                            (release / part["name"]).read_bytes()
                            for part in manifest["parts"]
                        )
                    )
                    replacement = directory / "replacement.zip"
                    with zipfile.ZipFile(original) as source, zipfile.ZipFile(
                        replacement, "w"
                    ) as target:
                        for entry in source.infolist():
                            if entry.filename != "databricks_port/warp_pdf.py":
                                target.writestr(entry, source.read(entry.filename))
                    content = replacement.read_bytes()
                    parts = []
                    for index, start in enumerate(
                        range(0, len(content), 8 * 1024 * 1024)
                    ):
                        chunk = content[start : start + 8 * 1024 * 1024]
                        name = f"replacement.zip.part{index:03d}"
                        (release / name).write_bytes(chunk)
                        parts.append(
                            {
                                "name": name,
                                "bytes": len(chunk),
                                "sha256": hashlib.sha256(chunk).hexdigest(),
                            }
                        )
                    manifest.update(
                        parts=parts,
                        archive_sha256=hashlib.sha256(content).hexdigest(),
                        source_files=manifest["source_files"] - 1,
                    )
                    (release / "release.json").write_text(json.dumps(manifest))
                    expected = "declared_overlay_missing"
                output = directory / "failure.json"
                result = self.run_gate(release, output)
                self.assertNotEqual(result.returncode, 0)
                report = json.loads(output.read_text())
                self.assertFalse(report["passed"])
                self.assertEqual(report["reason"], expected)

    def test_absent_skipped_and_failed_required_controls_stop_deployment(self):
        # A separate source fixture supplies real unittest outcomes at the CLI
        # boundary. It does not monkeypatch the gate or its subprocess results.
        for outcome in ("absent", "skipped", "failed"):
            with self.subTest(
                outcome=outcome
            ), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                fixture = directory / "source"
                files = (
                    "tools/verify_staged_runtime.py",
                    "tools/workstream_preflight.py",
                    "tests/test_warp_parser_integration.py",
                    "tests/fixtures/warp-layout-controls.json",
                    "upstream.lock.json",
                    "port/dependencies/warp/lock.json",
                    "port/runtime/launch.py",
                    "port/runtime/requirements.lock",
                )
                for name in files:
                    target = fixture / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, target)
                (fixture / "tests/__init__.py").touch()
                test_file = fixture / "tests/test_warp_parser_integration.py"
                content = test_file.read_text()
                method = "test_actual_staged_launcher_keeps_venv_through_both_directory_changes"
                if outcome == "absent":
                    content = content.replace("def " + method, "def removed_control")
                elif outcome == "skipped":
                    content = content.replace(
                        "    def " + method,
                        "    @unittest.skip('fixture unavailable')\n    def " + method,
                    )
                else:
                    content = content.replace(
                        "    def " + method + "(self):",
                        "    def "
                        + method
                        + "(self):\n        self.fail('fixture failure')",
                    )
                test_file.write_text(content)
                output = directory / "failure.json"
                result = self.run_gate(
                    Path(os.environ["WARP_TEST_STAGED_RELEASE"]),
                    output,
                    command=fixture / "tools/verify_staged_runtime.py",
                )
                self.assertNotEqual(result.returncode, 0)
                report = json.loads(output.read_text())
                self.assertFalse(report["passed"])
                self.assertEqual(report["reason"], "required_staged_launcher_failed")

    def test_exact_release_executes_the_required_launcher_control_without_skips(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "verified.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(COMMAND),
                    "--release",
                    os.environ["WARP_TEST_STAGED_RELEASE"],
                    "--python",
                    os.environ["WARP_GATE_TEST_PYTHON"],
                    "--output",
                    str(output),
                ],
                cwd=temporary,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(output.read_text())
            self.assertTrue(receipt["passed"])
            self.assertEqual(receipt["executed"], 1)
            self.assertEqual(receipt["skipped"], 0)
            self.assertEqual(
                receipt["checks"]["staged_launcher"]["test_ids"],
                [
                    "tests.test_warp_parser_integration.WarpLayoutControlTests."
                    "test_actual_staged_launcher_keeps_venv_through_both_directory_changes"
                ],
            )
