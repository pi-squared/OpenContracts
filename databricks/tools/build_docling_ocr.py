"""Retain stock RapidOCR code while replacing its GUI OpenCV dependency."""

import hashlib
import json
import zipfile
from pathlib import Path

if __package__:
    from .build_warp_runtime import _transition_version, _write_wheel
else:
    from build_warp_runtime import _transition_version, _write_wheel

ROOT = Path(__file__).resolve().parents[1]


def build(stock, destination):
    lock = json.loads((ROOT / "port/dependencies/docling/lock.json").read_text())
    if hashlib.sha256(stock.read_bytes()).hexdigest() != lock["stock_wheel_sha256"]:
        raise ValueError("RapidOCR input wheel differs from the pinned stock source")
    with zipfile.ZipFile(stock) as archive:
        files = {
            name: archive.read(name)
            for name in archive.namelist()
            if not name.endswith("/")
        }
    original_code = {
        name: content for name, content in files.items() if name.startswith("rapidocr/")
    }
    files, metadata = _transition_version(files, "rapidocr", "3.9.2", lock["version"])
    before = b"Requires-Dist: opencv_python>=4.5.1.48"
    if files[metadata].count(before) != 1:
        raise ValueError("RapidOCR stock OpenCV requirement changed")
    files[metadata] = files[metadata].replace(
        before, b"Requires-Dist: opencv-python-headless==4.12.0.88", 1
    )
    assert original_code == {
        name: content for name, content in files.items() if name.startswith("rapidocr/")
    }
    destination.mkdir(parents=True, exist_ok=False)
    output = _write_wheel(
        files, "rapidocr-" + lock["version"] + "-py3-none-any.whl", destination
    )
    if hashlib.sha256(output.read_bytes()).hexdigest() != lock["wheel_sha256"]:
        raise ValueError("Headless RapidOCR wheel differs from its retained build")
    return output
