"""Verify prepared application identity for frontend checks and release staging."""

import hashlib
import json
import subprocess
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_prepared(source: Path, port_root: Path):
    """Return the verified lock and tracked paths, rejecting unreviewed source."""
    lock = json.loads((port_root / "upstream.lock.json").read_text())
    for patch in lock.get("patches", []):
        if digest(port_root / patch["path"]) != patch["sha256"]:
            raise ValueError(f"Patch hash mismatch: {patch['path']}")
    for overlay in lock["overlays"]:
        if digest(port_root / overlay["source"]) != overlay["sha256"]:
            raise ValueError(f"Overlay hash mismatch: {overlay['source']}")
    actual = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != lock["commit"] or digest(source / "LICENSE") != lock["license_sha256"]:
        raise ValueError("Source revision or license differs from pinned release")
    for path, expected in lock["unchanged_stock_files"].items():
        if digest(source / path) != expected:
            raise ValueError(f"Protected upstream file differs: {path}")
    for overlay in lock["overlays"]:
        expected = lock["patched_files"].get(overlay["target"], overlay["sha256"])
        if digest(source / overlay["target"]) != expected:
            raise ValueError(f"Prepared overlay differs: {overlay['target']}")
    tracked = set(
        subprocess.check_output(
            ["git", "-C", str(source), "ls-files", "-z"], text=True
        ).split("\0")
    ) - {""}
    changed = set(
        subprocess.check_output(
            ["git", "-C", str(source), "diff", "HEAD", "--name-only"], text=True
        ).splitlines()
    )
    # New patches/overlays may be absent from the upstream index; their final
    # bytes are still verified below.
    if changed != set(lock["patched_files"]) & tracked:
        raise ValueError(
            "Prepared tracked modifications differ from the patch manifest"
        )
    for path, expected in lock["patched_files"].items():
        if digest(source / path) != expected:
            raise ValueError(f"Prepared patch content differs: {path}")
    return lock, tracked
