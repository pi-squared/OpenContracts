"""Assemble a hash-pinned patched Warp wheel and its frozen English resources."""

import argparse
import base64
import csv
import hashlib
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(content):
    return hashlib.sha256(content).hexdigest()


def _write_wheel(files, filename, destination):
    record_name = next(name for name in files if name.endswith(".dist-info/RECORD"))
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in sorted(files.items()):
        if name != record_name:
            encoded = (
                base64.urlsafe_b64encode(hashlib.sha256(content).digest())
                .decode()
                .rstrip("=")
            )
            writer.writerow([name, "sha256=" + encoded, len(content)])
    writer.writerow([record_name, "", ""])
    files[record_name] = record.getvalue().encode()
    output = destination / filename
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output


def _transition_version(files, distribution, upstream_version, version):
    old_info = f"{distribution}-{upstream_version}.dist-info"
    new_info = f"{distribution}-{version}.dist-info"
    files = {
        name.replace(old_info + "/", new_info + "/", 1): content
        for name, content in files.items()
    }
    metadata = new_info + "/METADATA"
    before = f"Version: {upstream_version}\n".encode()
    if files[metadata].count(before) != 1:
        raise ValueError(f"{distribution} wheel metadata version is unexpected")
    files[metadata] = files[metadata].replace(
        before, f"Version: {version}\n".encode(), 1
    )
    return files, metadata


def _headless_ocr(wheel, lock):
    content = wheel.read_bytes()
    if wheel.name != lock["wheel_filename"] or digest(content) != lock["wheel_sha256"]:
        raise ValueError("RapidOCR wheel differs from the pinned stock distribution")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    files, metadata = _transition_version(
        files, "rapidocr_onnxruntime", lock["upstream_version"], lock["version"]
    )
    requirement = lock["stock_requirement"].encode()
    if files[metadata].count(requirement) != 1:
        raise ValueError("RapidOCR wheel dependency metadata is unexpected")
    files[metadata] = files[metadata].replace(
        requirement, lock["headless_requirement"].encode(), 1
    )
    return files


def build(wheel, nltk_data, destination, *, root=ROOT, rapidocr_wheel=None):
    """Reject changed input bytes before writing a fresh dependency bundle."""
    lock_bytes = (root / "port/dependencies/warp/lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    if destination.exists():
        raise ValueError("Choose a fresh Warp runtime directory")
    ocr_files = None
    if "rapidocr" in lock:
        if rapidocr_wheel is None:
            raise ValueError("Warp runtime requires the pinned RapidOCR wheel")
        ocr_files = _headless_ocr(rapidocr_wheel, lock["rapidocr"])
    wheel_bytes = wheel.read_bytes()
    if (
        wheel.name != lock["wheel_filename"]
        or digest(wheel_bytes) != lock["wheel_sha256"]
    ):
        raise ValueError("Warp wheel differs from the pinned stock distribution")
    for item in lock["patches"]:
        if digest((root / item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("Warp patch differs from the dependency lock")
    assets = {}
    for name, expected in lock["nltk_assets"].items():
        assets[name] = (nltk_data / name).read_bytes()
        if digest(assets[name]) != expected:
            raise ValueError(f"Warp NLTK asset differs: {name}")
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
        files = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    for name, expected in lock["stock_files"].items():
        if digest(files[name]) != expected:
            raise ValueError(f"Warp stock source differs: {name}")
    with tempfile.TemporaryDirectory(prefix="opencontracts-warp-build-") as temporary:
        source = Path(temporary)
        for name, content in files.items():
            target = source / name
            if not target.resolve().is_relative_to(source.resolve()):
                raise ValueError("Warp wheel path escapes build directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        for item in lock["patches"]:
            patch = root / item["path"]
            subprocess.run(
                ["git", "apply", "--check", str(patch)], cwd=source, check=True
            )
            subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
        for name, expected in lock["patched_files"].items():
            files[name] = (source / name).read_bytes()
            if digest(files[name]) != expected:
                raise ValueError(f"Patched Warp source differs: {name}")

    files, _ = _transition_version(
        files, "warp_ingest", lock["upstream_version"], lock["version"]
    )
    destination.mkdir(parents=True)
    filename = f"warp_ingest-{lock['version']}-py3-none-any.whl"
    output = _write_wheel(files, filename, destination)
    for name, content in assets.items():
        target = destination / "nltk-data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    receipt = {
        "distribution": lock["distribution"],
        "version": lock["version"],
        "stock_wheel_sha256": lock["wheel_sha256"],
        "lock_sha256": digest(lock_bytes),
        "patches": lock["patches"],
        "wheel_filename": filename,
        "wheel_sha256": digest(output.read_bytes()),
        "source_files": {
            name: digest(content)
            for name, content in sorted(files.items())
            if name.startswith("warp_ingest/") and name.endswith(".py")
        },
        "nltk_assets": lock["nltk_assets"],
    }
    if ocr_files is not None:
        ocr = lock["rapidocr"]
        filename = f"rapidocr_onnxruntime-{ocr['version']}-py3-none-any.whl"
        output = _write_wheel(ocr_files, filename, destination)
        receipt["rapidocr"] = {
            "version": ocr["version"],
            "stock_wheel_sha256": ocr["wheel_sha256"],
            "wheel_filename": filename,
            "wheel_sha256": digest(output.read_bytes()),
            "headless_requirement": ocr["headless_requirement"],
            "package_files": {
                name: digest(content)
                for name, content in sorted(ocr_files.items())
                if name.startswith("rapidocr_onnxruntime/")
            },
        }
    (destination / "warp-runtime.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--nltk-data", type=Path, required=True)
    parser.add_argument("--rapidocr-wheel", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.wheel.resolve(),
                args.nltk_data.resolve(),
                args.destination.resolve(),
                rapidocr_wheel=args.rapidocr_wheel.resolve(),
            )
        )
    )
