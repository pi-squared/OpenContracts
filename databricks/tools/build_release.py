"""Fetch the fork's stock pin, apply its recipe, compile, stage and verify a release."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from prepare_upstream import prepare
from stage_app import stage

ROOT = Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("plan-promotion", "promote"):
        from release_promotion import main as promote_main

        return promote_main(sys.argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--app-origin")
    parser.add_argument("--installation-state-directory", type=Path)
    parser.add_argument("--development-commit")
    parser.add_argument("--node-bin", type=Path, required=True)
    parser.add_argument(
        "--runtime-python",
        type=Path,
        help="Existing verified runtime venv; omitted creates a new environment in the build directory",
    )
    parser.add_argument("--warp-wheel", type=Path, required=True)
    parser.add_argument("--rapidocr-wheel", type=Path, required=True)
    parser.add_argument("--warp-nltk-data", type=Path, required=True)
    parser.add_argument("--workflow-package-root")
    parser.add_argument("--docling-jobs", action="store_true")
    parser.add_argument("--configuration-resource", choices=("installation-config",))
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional verified local Git mirror; default fetches the fork",
    )
    args = parser.parse_args()
    if args.installation_state_directory:
        state = json.loads(
            (args.installation_state_directory / "installation.json").read_text()
        )
        if (
            state.get("phase") != "configured"
            or state.get("database_mode") != "existing"
        ):
            raise ValueError("Build needs a configured existing-state installation")
        selected = {
            "app_origin": state["app_url"].rstrip("/"),
            "workflow_package_root": state["runtime_configuration"][
                "WORKFLOW_PACKAGE_ROOT"
            ],
            "configuration_resource": "installation-config",
        }
        for name, value in selected.items():
            if getattr(args, name) not in (None, value):
                raise ValueError(
                    "Build configuration conflicts with its installation journal"
                )
            setattr(args, name, value)
    if not args.app_origin or not args.workflow_package_root:
        parser.error(
            "Select App origin and package root, directly or through the installation journal"
        )
    if args.development_commit:
        checkout = ROOT.parent
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=checkout, text=True
        ).strip()
        if head != args.development_commit or dirty:
            raise ValueError("Build must use the exact clean development commit")
    work = args.work_directory.absolute()
    if work.exists():
        raise ValueError("Choose a fresh build directory")
    work.mkdir(parents=True, mode=0o700)
    prepared = work / "prepared"
    prepare(prepared, args.source)
    node_bin = args.node_bin.absolute()
    environment = {
        **os.environ,
        "PATH": str(node_bin) + ":" + os.environ["PATH"],
        "COREPACK_ENABLE_AUTO_PIN": "0",
    }
    subprocess.run(
        [str(node_bin / "corepack"), "yarn", "install", "--frozen-lockfile"],
        cwd=prepared / "frontend",
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/test_frontend.py"),
            "--upstream",
            str(prepared),
            "--node-bin",
            str(node_bin),
            "--build",
            "--report",
            str(work / "frontend.json"),
        ],
        env=environment,
        check=True,
    )
    release = work / "release"
    stage(
        prepared,
        release,
        args.app_origin,
        args.workflow_package_root,
        warp_wheel=args.warp_wheel,
        warp_nltk_data=args.warp_nltk_data,
        rapidocr_wheel=args.rapidocr_wheel,
        docling_jobs=args.docling_jobs,
        configuration_resource=args.configuration_resource,
    )
    runtime_python = args.runtime_python
    if runtime_python is None:
        runtime = work / "runtime-venv"
        cache = work / "uv-cache"
        subprocess.run(
            [
                "uv",
                "--cache-dir",
                str(cache),
                "venv",
                "--python",
                sys.executable,
                str(runtime),
            ],
            check=True,
        )
        runtime_python = runtime / "bin/python"
        subprocess.run(
            [
                "uv",
                "--cache-dir",
                str(cache),
                "pip",
                "sync",
                "--python",
                str(runtime_python),
                "requirements.txt",
            ],
            cwd=release,
            check=True,
        )
    subprocess.run(
        [
            str(runtime_python),
            str(ROOT / "tools/verify_staged_runtime.py"),
            "--release",
            str(release),
            "--python",
            str(runtime_python),
            "--output",
            str(work / "runtime-gate.json"),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
