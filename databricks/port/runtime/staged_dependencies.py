"""Install exact staged wheels offline into an owned ephemeral source directory."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def install_vendor(manifest, runtime, python):
    if "warp_runtime" not in manifest:
        return
    parser = manifest["warp_runtime"]
    wheels = []
    for dependency in (parser, parser["rapidocr"]):
        name = dependency["wheel_filename"]
        if Path(name).name != name or not name.endswith(".whl"):
            raise ValueError("Invalid vendor wheel name")
        wheel = runtime / "vendor" / name
        if hashlib.sha256(wheel.read_bytes()).hexdigest() != dependency["wheel_sha256"]:
            raise ValueError("Vendor wheel checksum mismatch")
        wheels.append(str(wheel))
    subprocess.run(
        [
            os.path.abspath(python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-index",
            "--no-deps",
            "--no-cache-dir",
            "--no-compile",
            "--disable-pip-version-check",
            "--target",
            str(runtime),
            *wheels,
        ],
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    args = parser.parse_args()
    install_vendor(
        json.loads(args.manifest.read_text()), args.runtime.resolve(), sys.executable
    )
