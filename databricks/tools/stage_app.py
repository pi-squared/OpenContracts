"""Package a prepared pinned application and its production frontend, without inputs."""

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

if __package__:
    from .prepared_source import digest, verify_prepared
else:
    from prepared_source import digest, verify_prepared

ROOT = Path(__file__).resolve().parents[1]

if __package__:
    from .build_warp_runtime import build as build_warp
else:
    from build_warp_runtime import build as build_warp


def stage(
    source,
    destination,
    origin,
    workflow_package_root=None,
    tool_strict_mode="preserve",
    warp_wheel=None,
    warp_nltk_data=None,
    rapidocr_wheel=None,
    docling_jobs=False,
):
    if destination.exists():
        raise ValueError("Choose a fresh staging directory")
    lock, tracked = verify_prepared(source, ROOT)
    actual = lock["commit"]
    if not (source / "frontend/dist/index.html").is_file():
        raise ValueError("Production frontend build is required")
    if not origin.startswith("https://") or "/" in origin.removeprefix("https://"):
        raise ValueError("App origin must be an HTTPS origin")
    if workflow_package_root and (
        not workflow_package_root.startswith("/Volumes/")
        or ".." in Path(workflow_package_root).parts
        or len(Path(workflow_package_root).parts) < 5
    ):
        raise ValueError("Workflow package root must be a Unity Catalog volume path")
    warp_lock = ROOT / "port/dependencies/warp/lock.json"
    if warp_lock.exists() and any(
        value is None for value in (warp_wheel, warp_nltk_data, rapidocr_wheel)
    ):
        raise ValueError(
            "Patched Warp staging requires --warp-wheel, --warp-nltk-data and --rapidocr-wheel"
        )
    destination.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="opencontracts-stage-") as temp:
        payload = Path(temp) / "payload"
        payload.mkdir()
        selected = (
            tracked
            | {entry["target"] for entry in lock["overlays"]}
            | set(lock["patched_files"])
        )
        for name in sorted(selected):
            path = Path(name)
            if not name or path.parts[0] not in {
                "config",
                "opencontractserver",
                "locale",
                "databricks_port",
            }:
                continue
            if (
                "tests" in path.parts
                or path.name.startswith("test_")
                or path.suffix.lower()
                in {".pyc", ".pdf", ".jsonl", ".sqlite", ".sqlite3", ".csv", ".parquet"}
                or "cassettes" in path.parts
                or "fixtures" in path.parts
            ):
                continue
            target = payload / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, target)
        shutil.copytree(source / "frontend/dist", payload / "frontend/dist")
        shutil.copyfile(source / "app.py", payload / "app.py")
        shutil.copyfile(source / "LICENSE", payload / "LICENSE")
        shutil.copyfile(ROOT / "upstream.lock.json", payload / "upstream.lock.json")
        warp_runtime = None
        if warp_lock.exists():
            warp_bundle = Path(temp) / "warp"
            warp_runtime = build_warp(
                warp_wheel,
                warp_nltk_data,
                warp_bundle,
                root=ROOT,
                rapidocr_wheel=rapidocr_wheel,
            )
            assets = payload / "databricks_port/warp_assets"
            shutil.copytree(warp_bundle / "nltk-data", assets / "nltk-data")
            shutil.copyfile(
                warp_bundle / "warp-runtime.json", assets / "warp-runtime.json"
            )
            vendor = destination / "vendor"
            vendor.mkdir()
            shutil.copyfile(
                warp_bundle / warp_runtime["wheel_filename"],
                vendor / warp_runtime["wheel_filename"],
            )
            ocr_filename = warp_runtime["rapidocr"]["wheel_filename"]
            shutil.copyfile(warp_bundle / ocr_filename, vendor / ocr_filename)
        for path in payload.rglob("*"):
            if path.is_file() and path.suffix.lower() in {
                ".pdf",
                ".sqlite",
                ".sqlite3",
                ".csv",
                ".parquet",
            }:
                raise ValueError("Release contains document or processed data")
        archive_path = Path(temp) / "source.zip"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(payload.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(
                        path.relative_to(payload).as_posix(), (1980, 1, 1, 0, 0, 0)
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, path.read_bytes())
        parts = []
        with archive_path.open("rb") as archive:
            while data := archive.read(8 * 1024 * 1024):
                name = f"opencontracts.part{len(parts):03}"
                (destination / name).write_bytes(data)
                parts.append(
                    {
                        "name": name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        manifest = {
            "upstream_commit": actual,
            "lock_sha256": digest(ROOT / "upstream.lock.json"),
            "archive_sha256": digest(archive_path),
            "parts": parts,
            "requirements_sha256": digest(ROOT / "port/runtime/requirements.lock"),
            "source_files": sum(path.is_file() for path in payload.rglob("*")),
            "contains_domain_inputs": False,
        }
        if warp_runtime:
            manifest["warp_runtime"] = warp_runtime
        (destination / "release.json").write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copyfile(ROOT / "port/runtime/launch.py", destination / "app.py")
    shutil.copyfile(
        ROOT / "port/runtime/requirements.lock", destination / "requirements.txt"
    )
    config = yaml.safe_load((ROOT / "port/runtime/app.yaml").read_text())
    config["env"].append({"name": "APP_ORIGIN", "value": origin})
    if workflow_package_root:
        config["env"].append(
            {"name": "WORKFLOW_PACKAGE_ROOT", "value": workflow_package_root}
        )
    config["env"].append({"name": "DATABRICKS_TOOL_STRICT", "value": tool_strict_mode})
    if docling_jobs:
        config["env"].extend(
            [
                {"name": "DOCLING_JOB_ID", "valueFrom": "docling-job"},
                {"name": "DOCLING_ARTIFACT_ROOT", "valueFrom": "docling-artifacts"},
                {"name": "OPENCONTRACTS_WORKER_CONCURRENCY", "value": "4"},
            ]
        )
    (destination / "app.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--app-origin", required=True)
    parser.add_argument("--workflow-package-root")
    parser.add_argument("--warp-wheel", type=Path)
    parser.add_argument("--warp-nltk-data", type=Path)
    parser.add_argument("--rapidocr-wheel", type=Path)
    parser.add_argument("--docling-jobs", action="store_true")
    parser.add_argument(
        "--tool-strict-mode", choices=("preserve", "omit"), default="preserve"
    )
    args = parser.parse_args()
    stage(
        args.upstream.resolve(),
        args.destination.resolve(),
        args.app_origin,
        args.workflow_package_root,
        args.tool_strict_mode,
        args.warp_wheel,
        args.warp_nltk_data,
        args.rapidocr_wheel,
        args.docling_jobs,
    )
