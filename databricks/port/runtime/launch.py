"""Verify and unpack the staged pinned release into ephemeral app compute."""

import hashlib
import importlib.util
import json
import os
import runpy
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

package_dir = Path(__file__).resolve().parent
if "INSTALLATION_CONFIG_JSON" in os.environ:
    from installation_configuration import load_environment

    load_environment(os.environ)
manifest = json.loads((package_dir / "release.json").read_text())
runtime = Path(tempfile.mkdtemp(prefix="opencontracts-runtime-"))
archive_path = runtime / "source.zip"
with archive_path.open("wb") as target:
    for entry in manifest["parts"]:
        name = entry["name"]
        if Path(name).name != name:
            raise ValueError("Invalid release part name")
        part = package_dir / name
        if hashlib.sha256(part.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Release part checksum mismatch")
        with part.open("rb") as source:
            shutil.copyfileobj(source, target)
if hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
    raise ValueError("Release archive checksum mismatch")
with zipfile.ZipFile(archive_path) as archive:
    for name in archive.namelist():
        if not (runtime / name).resolve().is_relative_to(runtime):
            raise ValueError("Release archive path escapes runtime")
    archive.extractall(runtime)
archive_path.unlink()
# Databricks may report a relative virtualenv interpreter. Capture its path
# before changing cwd, retaining the virtualenv symlink for parser workers.
sys.executable = os.path.abspath(sys.executable)
installer = package_dir / "staged_dependencies.py"
installer_source = installer.read_bytes()
if (
    hashlib.sha256(installer_source).hexdigest()
    != manifest["dependency_installer_sha256"]
):
    raise ValueError("Dependency installer checksum mismatch")
spec = importlib.util.spec_from_file_location("staged_dependencies", installer)
if spec is None or spec.loader is None:
    raise ValueError("Dependency installer cannot be loaded")
dependency_installer = importlib.util.module_from_spec(spec)
# Execute the verified bytes without writing a cache into the release directory.
exec(compile(installer_source, str(installer), "exec"), dependency_installer.__dict__)
dependency_installer.install_vendor(manifest, runtime, sys.executable)
os.chdir(runtime)
sys.path.insert(0, str(runtime))
runpy.run_path(str(runtime / "app.py"), run_name="__main__")
