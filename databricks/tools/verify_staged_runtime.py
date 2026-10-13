"""Verify an exact staged runtime before its deployment; retain private results."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from .workstream_preflight import _open_receipt
except ImportError:
    from workstream_preflight import _open_receipt

ROOT = Path(__file__).resolve().parents[1]
CONTROL = (
    "tests.test_warp_parser_integration.WarpLayoutControlTests."
    "test_actual_staged_launcher_keeps_venv_through_both_directory_changes"
)
SOURCE_FILES = (
    "tools/verify_staged_runtime.py",
    "tools/workstream_preflight.py",
    "tests/test_warp_parser_integration.py",
    "tests/fixtures/warp-layout-controls.json",
    "upstream.lock.json",
    "port/dependencies/warp/lock.json",
    "port/runtime/launch.py",
    "port/runtime/staged_dependencies.py",
    "port/runtime/requirements.lock",
    "tools/installation_configuration.py",
)
IMPORTS = """
import json, sys
from pathlib import Path
from importlib import metadata
sys.path.insert(0, sys.argv[1])
from databricks_port import warp_pdf, parser_exports
assert all(module.__file__.startswith(sys.argv[1] + '/') for module in (warp_pdf, parser_exports))
assert callable(warp_pdf.parse_warp_pdf) and callable(parser_exports.warp_export)
vendor_origins = {name: str(metadata.distribution(name).locate_file(package))
                  for name, package in [('warp-ingest', 'warp_ingest'),
                                        ('rapidocr-onnxruntime', 'rapidocr_onnxruntime')]}
assert all(Path(origin).resolve().parent == Path(sys.argv[1]).resolve()
           for origin in vendor_origins.values())
print(json.dumps({'imports': ['databricks_port.warp_pdf', 'databricks_port.parser_exports'],
                  'version': warp_pdf.VERSION, 'vendor_origins': vendor_origins}))
"""
INSTALL = """
import json, runpy, sys
from pathlib import Path
installer, manifest, runtime = map(Path, sys.argv[1:4])
api = runpy.run_path(str(installer))
api['install_vendor'](json.loads(manifest.read_text()), runtime, sys.executable)
"""
PROBE = """
import json, sys
print(json.dumps({'version': list(sys.version_info[:3]), 'prefix': sys.prefix,
                  'base_prefix': sys.base_prefix, 'executable': sys.executable}))
"""
SMOKE = """
import json, os, sys, unittest
from pathlib import Path
root, release, extracted, output = map(Path, sys.argv[1:5])
control = sys.argv[5]
os.environ.update(WARP_TEST_ASSEMBLED_SOURCE=str(extracted),
                  WARP_RUNTIME_ROOT=str(extracted / 'databricks_port/warp_assets'),
                  WARP_TEST_STAGED_RELEASE=str(release))
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.loadTestsFromName(control)
def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item
identities = [case.id() for case in cases(suite)]
report = {'test_ids': identities, 'executed': 0, 'skipped': 0,
          'failures': 0, 'errors': 0, 'matched': identities == [control]}
if report['matched']:
    from databricks_port import warp_pdf
    assert Path(warp_pdf.__file__).parent.parent == extracted
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report.update(executed=result.testsRun - len(result.skipped), skipped=len(result.skipped),
                  failures=len(result.failures), errors=len(result.errors),
                  successful=result.wasSuccessful())
output.write_text(json.dumps(report))
sys.exit(0 if report.get('successful') and report['executed'] == 1 and report['skipped'] == 0 else 2)
"""


class GateFailure(ValueError):
    """A release cannot be admitted to deployment."""


def successful_required_control(smoke):
    return (
        isinstance(smoke, dict)
        and smoke.get("test_ids") == [CONTROL]
        and type(smoke.get("executed")) is int
        and smoke["executed"] == 1
        and type(smoke.get("skipped")) is int
        and smoke["skipped"] == 0
        and smoke.get("failures") == 0
        and smoke.get("errors") == 0
        and smoke.get("successful") is True
    )


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def inventory(release):
    if not release.is_dir():
        raise GateFailure("release_missing")
    if release.is_symlink():
        raise GateFailure("release_symlink")
    files = {}
    for path in sorted(release.rglob("*")):
        if path.is_symlink():
            raise GateFailure("staged_symlink")
        if path.is_file():
            files[path.relative_to(release).as_posix()] = digest(path)
    return files


def source_identity(source_root=ROOT):
    return {name: digest(source_root / name) for name in SOURCE_FILES}


def validate_release(release, directory):
    if not all(
        (release / name).is_file()
        for name in ("release.json", "app.py", "requirements.txt")
    ):
        raise GateFailure("release_inputs_missing")
    manifest = json.loads((release / "release.json").read_text())
    if "installation_configuration_sha256" in manifest and (
        digest(release / "installation_configuration.py")
        != manifest["installation_configuration_sha256"]
        or manifest["installation_configuration_sha256"]
        != digest(ROOT / "tools/installation_configuration.py")
    ):
        raise GateFailure("installation_configuration_source_mismatch")
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    if (
        manifest["lock_sha256"] != digest(ROOT / "upstream.lock.json")
        or manifest["upstream_commit"] != lock["commit"]
    ):
        raise GateFailure("release_source_mismatch")
    if digest(release / "app.py") != digest(ROOT / "port/runtime/launch.py"):
        raise GateFailure("launcher_source_mismatch")
    installer = release / "staged_dependencies.py"
    if (
        not installer.is_file()
        or digest(installer) != manifest.get("dependency_installer_sha256")
        or digest(installer) != digest(ROOT / "port/runtime/staged_dependencies.py")
    ):
        raise GateFailure("dependency_installer_source_mismatch")
    if digest(release / "requirements.txt") != manifest[
        "requirements_sha256"
    ] or manifest["requirements_sha256"] != digest(
        ROOT / "port/runtime/requirements.lock"
    ):
        raise GateFailure("requirements_source_mismatch")
    parts = manifest["parts"]
    if not isinstance(parts, list) or not 0 < len(parts) <= 64:
        raise GateFailure("archive_parts_missing")
    archive = directory / "source.zip"
    seen = set()
    with archive.open("wb") as stream:
        for part in parts:
            name = part["name"]
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or name in seen
                or type(part["bytes"]) is not int
                or not 0 < part["bytes"] <= 8 * 1024 * 1024
            ):
                raise GateFailure("archive_part_invalid")
            seen.add(name)
            path = release / name
            if path.stat().st_size != part["bytes"] or digest(path) != part["sha256"]:
                raise GateFailure("archive_part_changed")
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    stream.write(chunk)
    if digest(archive) != manifest["archive_sha256"]:
        raise GateFailure("archive_changed")
    extracted = directory / "extracted"
    extracted.mkdir()
    with zipfile.ZipFile(archive) as payload:
        names = payload.namelist()
        if len(set(names)) != len(names) or len(names) != manifest["source_files"]:
            raise GateFailure("archive_inventory_invalid")
        for item in payload.infolist():
            if (
                not (extracted / item.filename).resolve().is_relative_to(extracted)
                or (item.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise GateFailure("archive_path_invalid")
        for overlay in lock["overlays"]:
            target = overlay["target"]
            if not target.startswith(
                ("databricks_port/", "opencontractserver/", "config/")
            ):
                continue
            if target not in names:
                raise GateFailure("declared_overlay_missing")
            expected = lock.get("patched_files", {}).get(target, overlay["sha256"])
            if hashlib.sha256(payload.read(target)).hexdigest() != expected:
                raise GateFailure("declared_overlay_changed")
        payload.extractall(extracted)
    parser_lock = json.loads((ROOT / "port/dependencies/warp/lock.json").read_text())
    runtime = manifest["warp_runtime"]
    assets = extracted / "databricks_port/warp_assets"
    if (
        runtime != json.loads((assets / "warp-runtime.json").read_text())
        or runtime["lock_sha256"] != digest(ROOT / "port/dependencies/warp/lock.json")
        or runtime["version"] != parser_lock["version"]
    ):
        raise GateFailure("parser_runtime_mismatch")
    for vendor in (runtime, runtime["rapidocr"]):
        name = vendor["wheel_filename"]
        if (
            Path(name).name != name
            or digest(extracted / "vendor" / name) != vendor["wheel_sha256"]
        ):
            raise GateFailure("vendor_wheel_changed")
    if runtime["nltk_assets"] != parser_lock["nltk_assets"]:
        raise GateFailure("parser_resources_mismatch")
    for name, expected in parser_lock["nltk_assets"].items():
        if digest(assets / "nltk-data" / name) != expected:
            raise GateFailure("parser_resource_changed")
    return manifest, archive, extracted


def run_python(python, code, arguments, directory, diagnostics, name, timeout):
    environment = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LD_LIBRARY_PATH")
        if key in os.environ
    }
    result = subprocess.run(
        [str(python), "-I", "-c", code, *map(str, arguments)],
        cwd=directory,
        env=environment,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    (diagnostics / (name + ".stdout.log")).write_text(result.stdout)
    (diagnostics / (name + ".stderr.log")).write_text(result.stderr)
    return result


def verify(release, python, output, report):
    before = inventory(release)
    if output.resolve().is_relative_to(release.resolve()):
        raise GateFailure("receipt_inside_release")
    source = source_identity()
    report["source_files"] = source
    report["staged_files"] = before
    report["release_directory"] = str(release.resolve())
    report["source_directory"] = str(ROOT)
    report["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    python = Path(os.path.abspath(python))
    if not python.is_file():
        raise GateFailure("python_missing")
    diagnostics = output.with_name(output.stem + "-artifacts")
    diagnostics.mkdir(mode=0o700)
    report["diagnostics"] = str(diagnostics)
    with tempfile.TemporaryDirectory(prefix="staged-runtime-") as temporary:
        directory = Path(temporary)
        manifest, archive, extracted = validate_release(release, directory)
        report["release"] = {
            key: manifest[key]
            for key in (
                "upstream_commit",
                "lock_sha256",
                "archive_sha256",
                "source_files",
            )
        }
        report["release"].update(
            launcher_sha256=before["app.py"], manifest_sha256=before["release.json"]
        )
        result = run_python(python, PROBE, [], directory, diagnostics, "python", 30)
        if result.returncode:
            raise GateFailure("python_probe_failed")
        info = json.loads(result.stdout)
        if info["version"][:2] < [3, 11] or info["prefix"] == info["base_prefix"]:
            raise GateFailure("python_runtime_unsupported")
        report["python"] = info
        result = run_python(
            python,
            INSTALL,
            [release / "staged_dependencies.py", release / "release.json", extracted],
            directory,
            diagnostics,
            "vendor-install",
            120,
        )
        report["checks"]["vendor_install"] = {"actual_exit_code": result.returncode}
        if result.returncode:
            raise GateFailure("offline_vendor_install_failed")
        result = run_python(
            python, IMPORTS, [extracted], directory, diagnostics, "imports", 60
        )
        if result.returncode:
            raise GateFailure("isolated_archive_import_failed")
        imports = json.loads(result.stdout)
        if imports["imports"] != [
            "databricks_port.warp_pdf",
            "databricks_port.parser_exports",
        ]:
            raise GateFailure("isolated_archive_import_invalid")
        report["checks"]["isolated_archive_imports"] = imports
        result_file = directory / "smoke.json"
        result = run_python(
            python,
            SMOKE,
            [ROOT, release, extracted, result_file, CONTROL],
            directory,
            diagnostics,
            "staged-launcher",
            900,
        )
        smoke = json.loads(result_file.read_text())
        report["checks"]["staged_launcher"] = smoke
        report["executed"], report["skipped"] = smoke["executed"], smoke["skipped"]
        if result.returncode or not successful_required_control(smoke):
            raise GateFailure("required_staged_launcher_failed")
    if inventory(release) != before:
        raise GateFailure("release_changed_during_verification")
    if source_identity() != source:
        raise GateFailure("source_changed_during_verification")
    report.update(passed=True, reason="verified")


def revalidate(release, python, baseline, report, *, source_root=ROOT):
    if not baseline.is_file():
        raise GateFailure("receipt_missing")
    previous = json.loads(baseline.read_text())
    if not isinstance(previous, dict):
        raise GateFailure("receipt_not_verified")
    smoke = previous.get("checks", {}).get("staged_launcher", {})
    if (
        previous.get("schema_version") != 1
        or previous.get("passed") is not True
        or previous.get("reason") != "verified"
        or previous.get("executed") != 1
        or previous.get("skipped") != 0
        or not successful_required_control(smoke)
        or previous.get("checks", {}).get("isolated_archive_imports", {}).get("imports")
        != ["databricks_port.warp_pdf", "databricks_port.parser_exports"]
    ):
        raise GateFailure("receipt_not_verified")
    if (
        previous.get("release_directory") != str(release.resolve())
        or previous.get("source_directory") != str(source_root.resolve())
        or previous.get("python", {}).get("executable") != os.path.abspath(python)
    ):
        raise GateFailure("receipt_identity_mismatch")
    if previous.get("staged_files") != inventory(release):
        raise GateFailure("staged_files_changed")
    if previous.get("source_files") != source_identity(source_root):
        raise GateFailure("verification_source_changed")
    if not python.is_file():
        raise GateFailure("python_missing")
    baseline_hash = digest(baseline)
    report.update(previous)
    report.update(
        reason="receipt_revalidated",
        baseline_sha256=baseline_hash,
        revalidated_at_utc=datetime.now(timezone.utc).isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Revalidate a successful receipt before upload/deployment",
    )
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.release.resolve()):
        parser.exit(1, "Receipt output must be outside the staged release.\n")
    try:
        descriptor = _open_receipt(args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Cannot retain staged verification: {error}\n")
    os.umask(0o077)
    report = {
        "schema_version": 1,
        "passed": False,
        "executed": 0,
        "skipped": 0,
        "checks": {},
    }
    try:
        if args.receipt:
            revalidate(args.release.absolute(), args.python, args.receipt, report)
        else:
            verify(args.release.absolute(), args.python, args.output, report)
    except GateFailure as error:
        report.update(passed=False, reason=str(error))
    except subprocess.TimeoutExpired:
        report.update(passed=False, reason="verification_timeout")
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
        report.update(passed=False, reason="verification_input_or_result_invalid")
    with os.fdopen(descriptor, "w") as target:
        json.dump(report, target, indent=2)
        target.write("\n")
        target.flush()
        os.fsync(target.fileno())
    print(json.dumps({"receipt": str(args.output), "passed": report["passed"]}))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
