"""Create a fresh pinned checkout and apply the reviewed port patches in order."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from preserve_sources import restore_bundle

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(destination, source=None):
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    if destination.exists():
        raise ValueError("Destination already exists; choose a fresh checkout")
    for patch in lock["patches"]:
        if sha256(ROOT / patch["path"]) != patch["sha256"]:
            raise ValueError(f"Patch hash mismatch: {patch['path']}")
    for overlay in lock.get("overlays", []):
        if sha256(ROOT / overlay["source"]) != overlay["sha256"]:
            raise ValueError(f"Overlay hash mismatch: {overlay['source']}")
    if source is not None and source.suffix == ".bundle":
        shallow = source.with_suffix(".shallow")
        destination.parent.mkdir(parents=True, exist_ok=True)
        restore_bundle(destination, source, shallow if shallow.exists() else None)
        subprocess.run(
            [
                "git",
                "-C",
                str(destination),
                "remote",
                "add",
                "origin",
                lock["repository"],
            ],
            check=True,
        )
    else:
        subprocess.run(
            [
                "git",
                "clone",
                "--no-checkout",
                "--",
                str(source or lock["repository"]),
                str(destination),
            ],
            check=True,
        )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach", lock["commit"]],
        check=True,
    )
    actual = subprocess.check_output(
        ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
    ).strip()
    if (
        actual != lock["commit"]
        or sha256(destination / "LICENSE") != lock["license_sha256"]
    ):
        raise ValueError("Upstream source or license does not match the pin")
    for overlay in lock.get("overlays", []):
        target = destination / overlay["target"]
        if target.exists() or not target.resolve().is_relative_to(
            destination.resolve()
        ):
            raise ValueError(
                f"Overlay would overwrite stock source or escape checkout: {overlay['target']}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / overlay["source"], target)
    applied = []
    for patch in lock["patches"]:
        path = ROOT / patch["path"]
        subprocess.run(
            ["git", "-C", str(destination), "apply", "--check", str(path)], check=True
        )
        subprocess.run(["git", "-C", str(destination), "apply", str(path)], check=True)
        applied.append(patch["path"])
    for relative, expected in lock["unchanged_stock_files"].items():
        if sha256(destination / relative) != expected:
            raise ValueError(f"Protected stock source changed: {relative}")
    for relative, expected in lock.get("patched_files", {}).items():
        if sha256(destination / relative) != expected:
            raise ValueError(f"Prepared patch content differs: {relative}")
    receipt = {
        "upstream_commit": actual,
        "patches": applied,
        "stock_context_unchanged": True,
        "source": str(destination.resolve()),
    }
    print(json.dumps(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--source", type=Path, help="Optional local clone or preservation bundle"
    )
    args = parser.parse_args()
    prepare(args.destination.resolve(), args.source.resolve() if args.source else None)


if __name__ == "__main__":
    main()
