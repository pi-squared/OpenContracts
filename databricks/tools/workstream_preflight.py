"""Read-only workstream checkpoints; declarations never establish GitHub status."""

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PHASES = ("research", "diagnosis", "implementation", "review")


def _git(root, *args, optional=False):
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        capture_output=True,
    )
    if result.returncode and not optional:
        raise ValueError(f"Cannot read Git state: {args[0]}")
    return result.stdout


def _hash_file(path, *, follow_symlinks=False):
    if path.is_symlink() and not follow_symlinks:
        return hashlib.sha256(os.fsencode(os.readlink(path))).hexdigest()
    try:
        with path.open("rb") as source:
            digest = hashlib.sha256()
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
            return digest.hexdigest()
    except FileNotFoundError:
        return None


def _state(root):
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = iter(status.split(b"\0"))
    staged, unstaged, untracked = [], [], []
    for entry in entries:
        if not entry:
            continue
        flags, path = entry[:2].decode("ascii"), os.fsdecode(entry[3:])
        if "R" in flags or "C" in flags:
            next(entries)  # The second path is the original name.
        if flags == "??":
            untracked.append(path)
        else:
            if flags[0] != " ":
                staged.append(path)
            if flags[1] != " ":
                unstaged.append(path)
    index = _git(root, "diff", "--cached", "--binary", "--no-ext-diff", "--no-textconv")
    working = _git(root, "diff", "--binary", "--no-ext-diff", "--no-textconv")
    new_files = [(path, _hash_file(root / path)) for path in sorted(untracked)]
    changed = hashlib.sha256(
        status + index + working + json.dumps(new_files).encode()
    ).hexdigest()
    git_dir = Path(os.fsdecode(_git(root, "rev-parse", "--absolute-git-dir")).strip())
    common = Path(os.fsdecode(_git(root, "rev-parse", "--git-common-dir")).strip())
    if not common.is_absolute():
        common = root / common
    return {
        "worktree": str(root),
        "branch": os.fsdecode(
            _git(root, "symbolic-ref", "--short", "-q", "HEAD", optional=True)
        ).strip()
        or None,
        "head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "upstream_lock_sha256": (
            _hash_file(root / "databricks/upstream.lock.json")
            if (root / "databricks/upstream.lock.json").exists()
            else _hash_file(root / "upstream.lock.json")
        ),
        "isolated": git_dir.resolve() != common.resolve(),
        "staged": sorted(staged),
        "unstaged": sorted(unstaged),
        "untracked": sorted(untracked),
        "changes_sha256": changed,
    }


def _declaration(root, declaration):
    for field in ("owner", "purpose", "complete_when", "phase"):
        if (
            not isinstance(declaration.get(field), str)
            or not declaration[field].strip()
        ):
            raise ValueError(f"Declare {field}")
    if declaration["phase"] not in PHASES:
        raise ValueError("Unknown workstream phase")
    owner = declaration["owner"]
    if not re.fullmatch(
        r"https://github\.com/[\w.-]+/[\w.-]+/issues/[1-9][0-9]*", owner
    ):
        path = root / owner
        if (
            Path(owner).is_absolute()
            or not path.resolve().is_relative_to(root)
            or not path.is_file()
        ):
            raise ValueError(
                "Owner must be a GitHub issue URL or an existing repository-relative specification"
            )
    checks = declaration.get("checks", [])
    if not isinstance(checks, list) or any(
        not isinstance(c, str) or not c.strip() for c in checks
    ):
        raise ValueError("Checks must be a list of command descriptions")
    result = {
        field: declaration[field]
        for field in ("owner", "phase", "purpose", "complete_when")
    } | {"checks": checks}
    if "source_scope" in declaration:
        scope = declaration["source_scope"]
        if not isinstance(scope, dict) or not isinstance(scope.get("repository"), str):
            raise ValueError("Declare the source-scope repository")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", scope["repository"]):
            raise ValueError("Declare the source-scope repository as owner/name")
        if scope.get("mode", "implementation") not in ("implementation", "publication"):
            raise ValueError(
                "Unknown source-scope mode; use implementation or publication"
            )
        if scope.get("mode") == "publication" and "allowed_paths" not in scope:
            raise ValueError("Publication scope requires explicit allowed_paths")
        if "remote" in scope and (
            not isinstance(scope["remote"], str)
            or not re.fullmatch(r"[\w][\w.-]*", scope["remote"])
        ):
            raise ValueError(
                "Declare a symbolic remote name; connection URLs stay in Git configuration"
            )
        if type(scope.get("verify_remote", False)) is not bool:
            raise ValueError("verify_remote must be a JSON boolean")
        if not isinstance(scope.get("base_ref"), str) or not scope["base_ref"].strip():
            raise ValueError("Declare the intended base reference")
        for field in ("dependencies", "workstream_commits"):
            if not isinstance(scope.get(field, []), list) or any(
                not isinstance(ref, str) or not ref.strip()
                for ref in scope.get(field, [])
            ):
                raise ValueError(f"Declare {field} as commit references")
        if "allowed_paths" in scope:
            paths = scope["allowed_paths"]
            if not isinstance(paths, list) or any(
                not isinstance(pattern, str)
                or not pattern
                or Path(pattern).is_absolute()
                or ".." in Path(pattern).parts
                for pattern in paths
            ):
                raise ValueError("Declare repository-relative allowed path patterns")
        result["source_scope"] = json.loads(json.dumps(scope))
    return result


def _source_scope(root, declaration):
    scope = declaration.get("source_scope")
    if scope is None:
        return None, []
    base = (
        _git(
            root,
            "rev-parse",
            "--verify",
            "--end-of-options",
            scope["base_ref"] + "^{commit}",
        )
        .decode()
        .strip()
    )
    dependencies = [
        _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        .decode()
        .strip()
        for ref in scope.get("dependencies", [])
    ]
    workstream = [
        _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
        .decode()
        .strip()
        for ref in scope.get("workstream_commits", [])
    ]
    local_ref = scope.get(
        "local_main_ref", "refs/heads/" + scope.get("remote_branch", "main")
    )
    local_commit = (
        _git(
            root,
            "rev-parse",
            "--verify",
            "--end-of-options",
            local_ref + "^{commit}",
            optional=True,
        )
        .decode()
        .strip()
    )
    divergence = {
        "ref": local_ref,
        "commit": local_commit or None,
        "ahead": None,
        "behind": None,
    }
    if local_commit:
        behind, ahead = map(
            int,
            _git(
                root, "rev-list", "--left-right", "--count", base + "..." + local_commit
            ).split(),
        )
        divergence.update(ahead=ahead, behind=behind)
    inherited = _git(root, "rev-list", "HEAD", "--not", base).decode().splitlines()
    head_history = set(_git(root, "rev-list", "HEAD").decode().splitlines())
    missing_dependencies = sorted(set(dependencies) - head_history)
    dependency_history = set()
    for commit in dependencies:
        dependency_history.update(
            _git(root, "rev-list", commit, "--not", base).decode().splitlines()
        )
    unexpected = sorted(set(inherited) - dependency_history - set(workstream))
    remote = {"status": "unknown", "reason": "not_requested"}
    problems = ["unexpected_inherited_commits"] if unexpected else []
    if missing_dependencies:
        problems.append("declared_dependency_not_in_head")
    changed_paths = sorted(
        os.fsdecode(path)
        for path in _git(
            root, "diff", "--no-renames", "--name-only", "-z", base, "HEAD", "--"
        ).split(b"\0")
        if path
    )
    unexpected_paths = []
    if "allowed_paths" in scope:
        unexpected_paths = [
            path
            for path in changed_paths
            if not any(
                fnmatch.fnmatchcase(path, pattern) for pattern in scope["allowed_paths"]
            )
        ]
        if unexpected_paths:
            problems.append("unexpected_publication_paths")
    if scope.get("verify_remote"):
        remote = _observe_remote(root, scope)
        if remote["status"] != "verified":
            problems.append("remote_base_unverified")
        elif remote["commit"] != base:
            problems.append("remote_base_mismatch")
    elif scope.get("mode") == "publication":
        problems.append("remote_base_unverified")
    return {
        "repository": scope["repository"],
        "base_ref": scope["base_ref"],
        "base_commit": base,
        "dependencies": dependencies,
        "workstream_commits": workstream,
        "missing_dependencies": missing_dependencies,
        "local_main_divergence": divergence,
        "inherited_commits": inherited,
        "unexpected_commits": unexpected,
        "head": _git(root, "rev-parse", "HEAD").decode().strip(),
        "changed_paths": changed_paths,
        "unexpected_paths": unexpected_paths,
        "remote_verification": remote,
    }, problems


def _observe_remote(root, scope):
    if not isinstance(scope.get("remote"), str) or not scope["remote"].strip():
        raise ValueError("Declare the remote to verify")
    if (
        not isinstance(scope.get("remote_branch"), str)
        or not scope["remote_branch"].strip()
    ):
        raise ValueError("Declare the remote base branch")
    environment = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    environment.pop("GITHUB_TOKEN", None)
    environment.pop("GH_TOKEN", None)
    observed = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-remote",
                "--exit-code",
                "--",
                scope["remote"],
                "refs/heads/" + scope["remote_branch"],
            ],
            env=environment,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "unknown",
            "reason": "remote_read_failed",
            "observed_at_utc": observed,
        }
    rows = result.stdout.decode(errors="replace").splitlines()
    expected_ref = "refs/heads/" + scope["remote_branch"]
    matches = [
        row.split()[0]
        for row in rows
        if len(row.split()) == 2 and row.split()[1] == expected_ref
    ]
    if (
        result.returncode
        or len(matches) != 1
        or not re.fullmatch(r"[0-9a-f]{40}", matches[0])
    ):
        return {
            "status": "unknown",
            "reason": "remote_read_failed",
            "observed_at_utc": observed,
        }
    return {
        "status": "verified",
        "remote": scope["remote"],
        "branch": scope["remote_branch"],
        "commit": matches[0],
        "observed_at_utc": observed,
        "method": "git_ls_remote",
    }


def inspect(worktree, declaration, baseline=None):
    """Observe twice, preserve dirty state and expose movement since a checkpoint."""
    candidate = Path(worktree).resolve()
    root = Path(
        os.fsdecode(_git(candidate, "rev-parse", "--show-toplevel")).strip()
    ).resolve()
    declared = _declaration(root, declaration)
    before = _state(root)
    source_scope, scope_problems = _source_scope(root, declared)
    after = _state(root)
    stable = before == after
    problems = list(scope_problems)
    if not stable:
        problems.append("state_changed_during_capture")
    if not after["upstream_lock_sha256"]:
        problems.append("upstream_lock_missing")
    if declared["phase"] == "implementation" and (
        not after["isolated"] or not after["branch"]
    ):
        problems.append("implementation_requires_named_linked_worktree")
    differences = {}
    if baseline is not None:
        if (
            not isinstance(baseline, dict)
            or baseline.get("schema_version") != 1
            or baseline.get("stable") is not True
            or not isinstance(baseline.get("state"), dict)
            or not isinstance(baseline.get("declaration"), dict)
            or baseline.get("state", {}).get("worktree") != str(root)
            or baseline.get("declaration", {}).get("owner") != declared["owner"]
        ):
            raise ValueError(
                "Baseline must be a stable checkpoint for this working copy and owner"
            )
        for key in ("branch", "head", "upstream_lock_sha256", "changes_sha256"):
            if key not in baseline["state"]:
                raise ValueError("Baseline is missing source fingerprints")
            if baseline["state"][key] != after[key]:
                differences[key] = {
                    "before": baseline["state"][key],
                    "after": after[key],
                }
        if source_scope is not None:
            prior_scope = baseline.get("source_scope")
            if prior_scope is not None and not isinstance(prior_scope, dict):
                raise ValueError("Baseline source scope is malformed")
            if (
                differences
                or (prior_scope or {}).get("base_commit") != source_scope["base_commit"]
                or baseline["declaration"].get("source_scope")
                != declared["source_scope"]
            ):
                problems.append("source_scope_changed_since_baseline")
    report = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "declaration": declared,
        "issue_status": "unknown",
        "issue_status_source": "not_queried",
        "stable": stable,
        "checkpoint_valid": not problems,
        "problems": problems,
        "state": after,
        "baseline_changes": differences,
    }
    if source_scope is not None:
        report["source_scope"] = source_scope
    return report


def _open_receipt(output):
    if not output.is_absolute():
        raise ValueError("Use an absolute private receipt path")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.stat().st_mode & 0o077:
        raise ValueError("Receipt directory must be private (0700)")
    return os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)


def _emit_receipt(report, output, descriptor=None):
    encoded = json.dumps(report, indent=2) + "\n"
    if output:
        if descriptor is None:
            descriptor = _open_receipt(output)
        with os.fdopen(descriptor, "w") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        print(
            json.dumps(
                {
                    "receipt": str(output),
                    "stable": report["stable"],
                    "checkpoint_valid": report["checkpoint_valid"],
                }
            )
        )
    else:
        print(encoded, end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, default=Path.cwd())
    parser.add_argument("--owner", required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument("--complete-when", required=True)
    parser.add_argument("--check", action="append", default=[])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument(
        "--source-scope",
        type=Path,
        help="Private JSON declaring base, dependencies and publication scope",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        declaration = {
            "owner": args.owner,
            "phase": args.phase,
            "purpose": args.purpose,
            "complete_when": args.complete_when,
            "checks": args.check,
        }
        if args.source_scope:
            declaration["source_scope"] = json.loads(args.source_scope.read_text())
        baseline = json.loads(args.baseline.read_text()) if args.baseline else None
        report = inspect(args.worktree, declaration, baseline)
        _emit_receipt(report, args.output)
        return 0 if report["checkpoint_valid"] else 2
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Preflight failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
