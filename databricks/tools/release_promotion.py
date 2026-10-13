"""Git publication owned by build_release; assembly and runtime gates stay shared."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

if __package__:
    from .verify_staged_runtime import digest, inventory, revalidate
    from .workstream_preflight import _open_receipt
else:
    from verify_staged_runtime import digest, inventory, revalidate
    from workstream_preflight import _open_receipt

CANONICAL_REPOSITORY = "https://github.com/pi-squared/OpenContracts.git"
DEVELOPMENT_REPOSITORY = "pi-squared/OpenContracts-Databricks"
APP_PATH = "databricks/app"
PROMOTION_PATH = "databricks/promotion.json"
SOURCE_ROOTS = (
    "databricks",
    "GLOSSARY.md",
    "CHANGELOG.md",
    "docs/adr/0005-testing-git-promotion.md",
    "docs/test_scripts/testing-git-promotion.md",
)
APP_FILE_LIMIT = 10 * 1024 * 1024


def git(checkout, *arguments):
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("GITHUB_TOKEN", "GH_TOKEN")
    }
    return subprocess.check_output(
        ["git", "-C", str(checkout), *arguments],
        env=environment,
        text=True,
        timeout=120,
    ).strip()


def clean_head(checkout):
    if git(checkout, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Selected promotion checkout must be clean")
    return git(checkout, "rev-parse", "HEAD")


def remote_head(checkout, branch):
    value = git(checkout, "ls-remote", "origin", "refs/heads/" + branch)
    return value.split()[0] if value else None


def source_inventory(checkout, revision):
    paths = git(
        checkout, "ls-tree", "-r", "--name-only", revision, "--", *SOURCE_ROOTS
    ).splitlines()
    result = {}
    for name in paths:
        if name == PROMOTION_PATH or name.startswith(APP_PATH + "/"):
            continue
        path = checkout / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(
                "Maintained promotion source must contain regular tracked files"
            )
        result[name] = digest(path)
    if "databricks/upstream.lock.json" not in result:
        raise ValueError("Development source lacks a pinned Databricks recipe")
    return result


def retain(path, value):
    with os.fdopen(_open_receipt(path), "w") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def validated_release(release, python, receipt, *, source_root=None):
    report = {}
    if source_root is None:
        revalidate(release, python, receipt, report)
    else:
        revalidate(release, python, receipt, report, source_root=source_root)
    config = (release / "app.yaml").read_text()
    import yaml

    environment = yaml.safe_load(config)["env"]
    if {
        "name": "INSTALLATION_CONFIG_JSON",
        "valueFrom": "installation-config",
    } not in environment:
        raise ValueError("Git release must use bound installation configuration")
    if any(
        entry["name"]
        in (
            "APP_ORIGIN",
            "OPENCONTRACTS_SCHEMA",
            "OPENCONTRACTS_DATABASE_MODE",
            "PILOT_USERNAME",
            "WORKFLOW_PACKAGE_ROOT",
            "WORKFLOW_INSTALL_HASHES",
        )
        for entry in environment
    ):
        raise ValueError("Git release contains installation-specific configuration")
    for path in release.rglob("*"):
        if path.is_file() and path.stat().st_size > APP_FILE_LIMIT:
            raise ValueError("Git App file exceeds the Databricks 10 MB limit")
    return report


def plan(args):
    source = args.development_checkout.resolve()
    destination = args.destination_checkout.resolve()
    if source == destination:
        raise ValueError("Development and testing promotion need separate checkouts")
    head = clean_head(source)
    if head != args.development_commit:
        raise ValueError("Development HEAD differs from the selected verified commit")
    if git(destination, "config", "--get", "remote.origin.url") != CANONICAL_REPOSITORY:
        raise ValueError("Testing destination is not the canonical OpenContracts fork")
    if git(destination, "branch", "--show-current") != args.testing_branch:
        raise ValueError("Destination checkout is on another testing branch")
    destination_head = clean_head(destination)
    release, receipt = args.release.resolve(), args.receipt.resolve()
    validated_release(
        release, args.runtime_python, receipt, source_root=source / "databricks"
    )
    sources = source_inventory(source, head)
    manifest = json.loads((release / "release.json").read_text())
    if manifest["lock_sha256"] != sources["databricks/upstream.lock.json"]:
        raise ValueError("Release recipe differs from the selected development source")
    value = {
        "format": "opencontracts-testing-promotion.v1",
        "development_repository": DEVELOPMENT_REPOSITORY,
        "development_checkout": str(source),
        "development_commit": head,
        "destination_checkout": str(destination),
        "destination_repository": "pi-squared/OpenContracts",
        "testing_branch": args.testing_branch,
        "destination_head": destination_head,
        "remote_head": remote_head(destination, args.testing_branch),
        "source_files": sources,
        "release": str(release),
        "release_files": inventory(release),
        "runtime_python": os.path.abspath(args.runtime_python),
        "gate_receipt": str(receipt),
        "gate_sha256": digest(receipt),
        "recipe_sha256": manifest["lock_sha256"],
        "archive_sha256": manifest["archive_sha256"],
        "app_path": APP_PATH,
    }
    retain(args.output, value)
    print(
        json.dumps(
            {
                "planned": True,
                "development_commit": head,
                "testing_branch": args.testing_branch,
            }
        )
    )


def publication_record(value):
    return {
        key: value[key]
        for key in (
            "format",
            "development_repository",
            "development_commit",
            "destination_repository",
            "testing_branch",
            "source_files",
            "release_files",
            "gate_sha256",
            "recipe_sha256",
            "archive_sha256",
            "app_path",
        )
    }


def check_staged_whitespace(checkout, sources):
    """Only pinned patch hunk context may retain its required blank prefix."""
    lock = json.loads((checkout / "databricks/upstream.lock.json").read_text())
    blank_context_lines = {}
    for entry in lock["patches"]:
        relative = Path(entry["path"])
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or relative.parts[0] != "patches"
            or relative.suffix != ".patch"
        ):
            raise ValueError("Whitespace exception requires a maintained patch path")
        name = "databricks/" + relative.as_posix()
        path = checkout / name
        if (
            sources.get(name) != entry["sha256"]
            or digest(path) != entry["sha256"]
            or git(checkout, "hash-object", "--no-filters", "--", str(path))
            != git(checkout, "rev-parse", ":" + name)
        ):
            raise ValueError(
                "Whitespace exception requires exact hash-pinned staged patch bytes"
            )
        remaining = None
        blank_lines = set()
        for number, line in enumerate(path.read_text().splitlines(), 1):
            header = re.fullmatch(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@.*", line)
            if header:
                if remaining is not None:
                    raise ValueError("Pinned patch has an incomplete context hunk")
                remaining = tuple(
                    int(count) if count is not None else 1 for count in header.groups()
                )
                continue
            if line.rstrip(" \t") != line and (
                line != " " or remaining is None or min(remaining) <= 0
            ):
                raise ValueError("Pinned patch contains invalid trailing whitespace")
            if line == " ":
                blank_lines.add(number)
            if remaining is not None and line != "\\ No newline at end of file":
                if not line or line[0] not in " +-":
                    raise ValueError("Pinned patch has invalid context hunk syntax")
                old, new = remaining
                old -= int(line[0] in " -")
                new -= int(line[0] in " +")
                if min(old, new) < 0:
                    raise ValueError("Pinned patch has invalid context hunk counts")
                remaining = (old, new) if old or new else None
        if remaining is not None:
            raise ValueError("Pinned patch has an incomplete context hunk")
        git(checkout, "apply", "--stat", "--", str(path))
        blank_context_lines[name] = blank_lines
    # Run the complete ordinary Git check. Admit only its exact diagnostics
    # for the structurally verified context prefixes; every other fault fails.
    try:
        git(checkout, "diff", "--cached", "--check")
    except subprocess.CalledProcessError as error:
        lines = error.output.splitlines()
        if error.returncode != 2 or not lines:
            raise
        index = 0
        while index < len(lines):
            diagnostic = re.fullmatch(
                r"(.+):(\d+): (trailing whitespace|new blank line at EOF)\.",
                lines[index],
            )
            if diagnostic is None or int(diagnostic[2]) not in blank_context_lines.get(
                diagnostic[1], set()
            ):
                raise
            if diagnostic[3] == "trailing whitespace":
                if index + 1 >= len(lines) or lines[index + 1] != "+ ":
                    raise
                index += 2
            else:
                index += 1


def promote(args):
    value = json.loads(args.plan.read_text())
    if value.get("format") != "opencontracts-testing-promotion.v1":
        raise ValueError("Unsupported promotion plan")
    source, destination, release = map(
        Path,
        (
            value["development_checkout"],
            value["destination_checkout"],
            value["release"],
        ),
    )
    if (
        clean_head(source) != value["development_commit"]
        or source_inventory(source, value["development_commit"])
        != value["source_files"]
    ):
        raise ValueError("Development source changed after promotion planning")
    if (
        digest(Path(value["gate_receipt"])) != value["gate_sha256"]
        or inventory(release) != value["release_files"]
    ):
        raise ValueError("Release or gate changed after promotion planning")
    validated_release(
        release,
        Path(value["runtime_python"]),
        Path(value["gate_receipt"]),
        source_root=source / "databricks",
    )
    if (
        git(destination, "config", "--get", "remote.origin.url") != CANONICAL_REPOSITORY
        or git(destination, "branch", "--show-current") != value["testing_branch"]
    ):
        raise ValueError("Testing destination selection changed")
    current = clean_head(destination)
    published = destination / PROMOTION_PATH
    record = publication_record(value)
    accepted_path = args.plan.with_name(args.plan.name + ".accepted.json")
    if published.is_file() and json.loads(published.read_text()) == record:
        if not accepted_path.is_file():
            raise ValueError(
                "Previously promoted identity is missing; inspect publication"
            )
        accepted = json.loads(accepted_path.read_text())
        if (
            accepted["plan_sha256"] != digest(args.plan)
            or accepted["head"] != current
            or accepted["tree"] != git(destination, "rev-parse", "HEAD^{tree}")
            or source_inventory(destination, current) != value["source_files"]
        ):
            raise ValueError("Previously promoted source changed")
        if remote_head(destination, value["testing_branch"]) != current:
            raise ValueError(
                "Previously promoted remote branch differs from local HEAD"
            )
        if inventory(destination / APP_PATH) != value["release_files"]:
            raise ValueError(
                "Previously promoted runtime differs from the gated release"
            )
        retain(
            args.output,
            {
                "published": True,
                "unchanged": True,
                "head": current,
                "tree": accepted["tree"],
                "remote_exact": True,
                "promotion": record,
            },
        )
        print(json.dumps({"published": True, "unchanged": True, "head": current}))
        return
    if accepted_path.exists():
        raise ValueError("Previously promoted source changed")
    if (
        current != value["destination_head"]
        or remote_head(destination, value["testing_branch"]) != value["remote_head"]
    ):
        raise ValueError("Testing branch moved after promotion planning")
    old = git(
        destination, "ls-tree", "-r", "--name-only", current, "--", *SOURCE_ROOTS
    ).splitlines()
    selected = (
        set(value["source_files"])
        | {PROMOTION_PATH}
        | {APP_PATH + "/" + name for name in value["release_files"]}
    )
    for name in old:
        if name not in selected:
            git(destination, "rm", "--", name)
    app = destination / APP_PATH
    if app.exists():
        tracked = {
            name.removeprefix(APP_PATH + "/")
            for name in old
            if name.startswith(APP_PATH + "/")
        }
        if set(inventory(app)) - tracked:
            raise ValueError(
                "Testing app directory contains untracked or ignored artifacts"
            )
        shutil.rmtree(app)
    for name in value["source_files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    shutil.copytree(release, app)
    published.write_text(json.dumps(record, indent=2) + "\n")
    if inventory(app) != value["release_files"]:
        raise ValueError("Copied Git runtime differs from the gated release")
    git(destination, "add", "--", *sorted(selected))
    check_staged_whitespace(destination, value["source_files"])
    staged = set(git(destination, "diff", "--cached", "--name-only").splitlines())
    if staged - (set(old) | selected):
        raise ValueError("Promotion staged an undeclared path")
    if (
        clean_head(source) != value["development_commit"]
        or inventory(release) != value["release_files"]
    ):
        raise ValueError("Verified source changed adjacent to publication")
    if remote_head(destination, value["testing_branch"]) != value["remote_head"]:
        raise ValueError("Testing remote moved adjacent to publication")
    git(
        destination,
        "commit",
        "-m",
        "Promote verified Databricks testing release (#126)",
    )
    head = git(destination, "rev-parse", "HEAD")
    git(
        destination,
        "push",
        "-u",
        "origin",
        "HEAD:refs/heads/" + value["testing_branch"],
    )
    if remote_head(destination, value["testing_branch"]) != head:
        raise ValueError("Remote testing branch does not equal the promoted commit")
    tree = git(destination, "rev-parse", "HEAD^{tree}")
    if source_inventory(destination, head) != value["source_files"]:
        raise ValueError("Promoted maintained source differs from the verified source")
    retain(
        accepted_path,
        {"plan_sha256": digest(args.plan), "head": head, "tree": tree},
    )
    retain(
        args.output,
        {
            "published": True,
            "unchanged": False,
            "head": head,
            "tree": tree,
            "remote_exact": True,
            "promotion": record,
        },
    )
    print(
        json.dumps(
            {"published": True, "head": head, "testing_branch": value["testing_branch"]}
        )
    )


def main(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planned = commands.add_parser("plan-promotion")
    planned.add_argument("--development-checkout", type=Path, required=True)
    planned.add_argument("--development-commit", required=True)
    planned.add_argument("--destination-checkout", type=Path, required=True)
    planned.add_argument("--testing-branch", required=True)
    planned.add_argument("--release", type=Path, required=True)
    planned.add_argument("--receipt", type=Path, required=True)
    planned.add_argument("--runtime-python", type=Path, required=True)
    planned.add_argument("--output", type=Path, required=True)
    planned.set_defaults(run=plan)
    promoted = commands.add_parser("promote")
    promoted.add_argument("--plan", type=Path, required=True)
    promoted.add_argument("--output", type=Path, required=True)
    promoted.set_defaults(run=promote)
    args = parser.parse_args(arguments)
    os.umask(0o077)
    args.run(args)
