"""Run port integration checks against a prepared pinned upstream frontend."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .prepared_source import verify_prepared
else:
    from prepared_source import verify_prepared

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--node-bin", type=Path, required=True)
    parser.add_argument("--test", help="Optional test filename")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Run upstream TypeScript/production build after tests",
    )
    parser.add_argument(
        "--report", type=Path, help="Write test totals and build status as JSON"
    )
    args = parser.parse_args(argv)
    frontend = args.upstream.resolve() / "frontend"
    try:
        lock, _ = verify_prepared(args.upstream.resolve(), ROOT)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    node = args.node_bin.resolve() / "node"
    if not node.is_file():
        parser.error(
            "Selected Node executable is missing; provide --node-bin explicitly"
        )
    try:
        version = subprocess.run(
            [str(node), "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        parser.error("Cannot run the selected Node executable")
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", version)
    if not match or tuple(map(int, match.groups())) < (22, 16, 0):
        parser.error("Node 22.16 or later is required")
    for required in (
        "node_modules/vitest/vitest.mjs",
        "node_modules/jsdom/package.json",
    ):
        if not (frontend / required).is_file():
            parser.error(
                f"Missing frontend prerequisite: {required}; install with Corepack Yarn"
            )
    corepack = args.node_bin.resolve() / "corepack"
    if args.build and not corepack.is_file():
        parser.error("Missing frontend prerequisite: selected Corepack executable")
    tests = sorted((ROOT / "tests/frontend").glob(args.test or "*.test.tsx"))
    if not tests:
        parser.error("No matching frontend tests")
    with tempfile.TemporaryDirectory(prefix="port-tests-", dir=frontend) as temporary:
        destination = Path(temporary)
        for test in tests:
            shutil.copyfile(test, destination / test.name)
        config = destination / "vitest.config.mts"
        config.write_text(
            "import { defineConfig } from 'vitest/config';\n"
            "export default defineConfig({ server: { host: '127.0.0.1' }, "
            "test: { environment: 'jsdom', include: ['"
            + destination.name
            + "/*.test.tsx'] } });\n"
        )
        env = {
            **os.environ,
            "PATH": str(args.node_bin.resolve()) + ":" + os.environ["PATH"],
            "COREPACK_ENABLE_AUTO_PIN": "0",
        }
        report = destination / "results.json"
        vitest_code = subprocess.run(
            [
                str(node),
                "node_modules/vitest/vitest.mjs",
                "run",
                "--config",
                str(config),
                "--reporter=default",
                "--reporter=json",
                "--outputFile",
                str(report),
            ],
            cwd=frontend,
            env=env,
        ).returncode
        try:
            results = json.loads(report.read_text())
            counts = [
                results[key]
                for key in (
                    "numTotalTests",
                    "numPassedTests",
                    "numFailedTests",
                    "numPendingTests",
                    "numTodoTests",
                )
            ]
            if any(type(count) is not int or count < 0 for count in counts) or counts[
                0
            ] != sum(counts[1:]):
                raise ValueError("inconsistent test counts")
            if not isinstance(results["testResults"], list) or (
                counts[0] and not results["testResults"]
            ):
                raise ValueError("missing test files")
            if type(results["success"]) is not bool:
                raise ValueError("missing success status")
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f"Invalid frontend result report: {error}")
        skipped = results["numPendingTests"] + results["numTodoTests"]
        summary = {
            "upstream_commit": lock["commit"],
            "node": version,
            "tests": {
                "files": len(results["testResults"]),
                "executed": results["numTotalTests"] - skipped,
                "passed": results["numPassedTests"],
                "failed": results["numFailedTests"],
                "required_skips": skipped,
                "optional_skips": [],
            },
            "build": "not_run" if args.build else "not_requested",
        }
        failure = None
        if vitest_code or results["success"] is not True or results["numFailedTests"]:
            failure = "Frontend regressions failed"
        elif results["numTotalTests"] == 0:
            failure = "No frontend tests executed"
        elif skipped:
            failure = "Required frontend tests were skipped"
        exit_code = (vitest_code if vitest_code > 0 else 1) if failure else 0
        if not failure and args.build:
            exit_code = subprocess.run(
                [str(corepack), "yarn", "build"], cwd=frontend, env=env
            ).returncode
            summary["build"] = "failed" if exit_code else "passed"
        if args.report:
            args.report.write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps(summary))
        if failure:
            print(failure, file=sys.stderr)
        if exit_code:
            raise SystemExit(exit_code if exit_code > 0 else 1)
    return 0


if __name__ == "__main__":
    main()
