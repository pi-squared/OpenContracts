"""Preserve Git history, dirty indexes/worktrees and explicit private artifacts.

No source repository is modified. Archives are private, and verification reads
every archived file; a Git bundle alone does not preserve unpublished work.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    )


def digest(stream):
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return value.hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return digest(stream)


def worktrees(root):
    records = git(root, "worktree", "list", "--porcelain").decode().split("\n\n")
    return [Path(record.splitlines()[0][9:]) for record in records if record]


def restore_bundle(destination, bundle, shallow=None):
    """Reconstruct full or shallow history in an isolated repository."""
    subprocess.run(["git", "init", str(destination)], check=True, capture_output=True)
    if shallow is not None:
        shutil.copyfile(shallow, destination / ".git/shallow")
    refs = git(destination, "bundle", "unbundle", str(bundle)).decode().splitlines()
    updates = "".join(
        f"update {ref} {sha}\n"
        for sha, ref in (line.split(" ", 1) for line in refs)
        if ref.startswith("refs/")
    )
    subprocess.run(
        ["git", "-C", str(destination), "update-ref", "--stdin"],
        input=updates.encode(),
        check=True,
        capture_output=True,
    )
    head = next(
        sha for sha, ref in (line.split(" ", 1) for line in refs) if ref == "HEAD"
    )
    subprocess.run(
        ["git", "-C", str(destination), "update-ref", "--no-deref", "HEAD", head],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(destination), "fsck", "--connectivity-only", "--no-dangling"],
        check=True,
        capture_output=True,
    )


def archive_tree(root, paths, destination):
    entries = []
    with tarfile.open(destination, "w") as archive:
        for relative in sorted(set(paths)):
            path = root / relative
            if not path.exists() and not path.is_symlink():
                entries.append({"path": relative, "kind": "deleted"})
                continue
            if path.is_symlink():
                entry = {
                    "path": relative,
                    "kind": "symlink",
                    "target": os.readlink(path),
                }
            elif path.is_file():
                entry = {
                    "path": relative,
                    "kind": "file",
                    "sha256": file_digest(path),
                    "bytes": path.stat().st_size,
                    "mode": path.stat().st_mode & 0o777,
                }
            else:
                raise ValueError(f"Unsupported snapshot entry: {path}")
            archive.add(path, arcname=relative, recursive=False)
            entries.append(entry)
    return {
        "archive": destination.name,
        "sha256": file_digest(destination),
        "entries": entries,
    }


def snapshot(destination, repositories, artifacts):
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = {"format_version": 1, "repositories": [], "trees": [], "artifacts": []}
    for number, root in enumerate(repositories):
        root = root.resolve()
        name = f"repository-{number:02}"
        refs = git(root, "show-ref").decode()
        bundle = destination / f"{name}.bundle"
        git(root, "bundle", "create", str(bundle), "--all", "HEAD")
        git(root, "bundle", "verify", str(bundle))
        repository = {
            "source": str(root),
            "bundle": bundle.name,
            "sha256": file_digest(bundle),
            "refs": refs,
        }
        if git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
            shallow_path = Path(
                os.fsdecode(git(root, "rev-parse", "--git-path", "shallow").strip())
            )
            if not shallow_path.is_absolute():
                shallow_path = root / shallow_path
            shallow = destination / f"{name}.shallow"
            shutil.copyfile(shallow_path, shallow)
            repository["shallow"] = shallow.name
        manifest["repositories"].append(repository)
        for index, tree in enumerate(worktrees(root)):
            prefix = f"{name}-worktree-{index:02}"
            status = git(tree, "status", "--porcelain=v1", "-z")
            git_dir = Path(
                git(tree, "rev-parse", "--absolute-git-dir").decode().strip()
            )
            private_index = destination / f"{prefix}.index"
            shutil.copyfile(git_dir / "index", private_index)
            for kind, args in [
                ("staged", ("diff", "--cached", "--binary")),
                ("unstaged", ("diff", "--binary")),
            ]:
                (destination / f"{prefix}-{kind}.patch").write_bytes(git(tree, *args))
            paths = git(
                tree, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
            )
            paths = [os.fsdecode(path) for path in paths.split(b"\0") if path]
            record = archive_tree(tree, paths, destination / f"{prefix}.tar")
            record.update(
                {
                    "source": str(tree),
                    "head": git(tree, "rev-parse", "HEAD").decode().strip(),
                    "status_hex": status.hex(),
                    "index": private_index.name,
                    "index_sha256": file_digest(private_index),
                }
            )
            if status != git(tree, "status", "--porcelain=v1", "-z"):
                raise RuntimeError(f"Source status changed while archiving: {tree}")
            if file_digest(git_dir / "index") != record["index_sha256"]:
                raise RuntimeError(f"Source index changed while archiving: {tree}")
            if refs != git(root, "show-ref").decode():
                raise RuntimeError(f"Source refs changed while archiving: {root}")
            manifest["trees"].append(record)
            print(
                json.dumps(
                    {"preserved_worktree": str(tree), "entries": len(record["entries"])}
                ),
                flush=True,
            )
    for number, source in enumerate(artifacts):
        source = source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        root = source if source.is_dir() else source.parent
        paths = (
            [
                str(path.relative_to(root))
                for path in source.rglob("*")
                if path.is_file() or path.is_symlink()
            ]
            if source.is_dir()
            else [source.name]
        )
        record = archive_tree(root, paths, destination / f"artifact-{number:02}.tar")
        record["source"] = str(source)
        manifest["artifacts"].append(record)
        print(
            json.dumps(
                {"preserved_artifact": str(source), "entries": len(record["entries"])}
            ),
            flush=True,
        )
    # Hash indexes and patches too, so preserving staged state is verifiable.
    manifest["support_files"] = {
        path.name: file_digest(path)
        for path in destination.iterdir()
        if path.suffix in {".index", ".patch", ".shallow"}
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    verify(destination)


def verify(destination):
    manifest = json.loads((destination / "manifest.json").read_text())
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported archive format")
    for record in manifest["repositories"]:
        bundle = destination / record["bundle"]
        if file_digest(bundle) != record["sha256"]:
            raise ValueError(f"Bundle hash mismatch: {bundle.name}")
        # list-heads works without depending on the continued existence of the source repo.
        heads = subprocess.check_output(
            ["git", "bundle", "list-heads", str(bundle)]
        ).decode()
        for ref in record["refs"].splitlines():
            if ref not in heads.splitlines():
                raise ValueError(f"Ref missing from bundle: {ref}")
        shallow = destination / record["shallow"] if record.get("shallow") else None
        if (
            shallow is not None
            and file_digest(shallow) != manifest["support_files"][shallow.name]
        ):
            raise ValueError(f"Shallow boundary hash mismatch: {shallow.name}")
        with tempfile.TemporaryDirectory(prefix="oc-verify-history-") as temporary:
            restore_bundle(Path(temporary) / "repository", bundle.resolve(), shallow)
    files, byte_count = 0, 0
    for record in manifest["trees"] + manifest["artifacts"]:
        path = destination / record["archive"]
        if file_digest(path) != record["sha256"]:
            raise ValueError(f"Archive hash mismatch: {path.name}")
        expected = {
            entry["path"]: entry
            for entry in record["entries"]
            if entry["kind"] != "deleted"
        }
        with tarfile.open(path, "r") as archive:
            seen = set()
            for member in archive:
                if member.name in seen or member.name not in expected:
                    raise ValueError(f"Unexpected or duplicate member: {member.name}")
                seen.add(member.name)
                entry = expected[member.name]
                if entry["kind"] == "symlink":
                    if not member.issym() or member.linkname != entry["target"]:
                        raise ValueError(f"Symlink mismatch: {member.name}")
                else:
                    if (
                        not member.isfile()
                        or member.size != entry["bytes"]
                        or member.mode != entry["mode"]
                    ):
                        raise ValueError(f"Metadata mismatch: {member.name}")
                    with archive.extractfile(member) as stream:
                        if digest(stream) != entry["sha256"]:
                            raise ValueError(f"Content mismatch: {member.name}")
                    files += 1
                    byte_count += member.size
            if seen != set(expected):
                raise ValueError(f"Missing archive members: {path.name}")
    for name, sha256 in manifest["support_files"].items():
        if file_digest(destination / name) != sha256:
            raise ValueError(f"Support-file hash mismatch: {name}")
    receipt = {
        "verified": True,
        "manifest_sha256": file_digest(destination / "manifest.json"),
        "repositories": len(manifest["repositories"]),
        "worktrees": len(manifest["trees"]),
        "artifacts": len(manifest["artifacts"]),
        "files": files,
        "source_bytes": byte_count,
    }
    (destination / "verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    return receipt


def restore_worktree(archive_root, source, destination):
    """Restore one saved working copy and verify its files and staged state."""
    archive_root, source, destination = map(Path, (archive_root, source, destination))
    if destination.exists():
        raise FileExistsError(destination)
    manifest = json.loads((archive_root / "manifest.json").read_text())
    # The recorded path is historical identity even when that path now aliases
    # another working copy. Resolve only as a fallback for a new alias spelling.
    recorded = os.path.abspath(source)
    tree = next(
        (record for record in manifest["trees"] if record["source"] == recorded), None
    )
    if tree is None:
        tree = next(
            record
            for record in manifest["trees"]
            if record["source"] == str(source.resolve())
        )
    prefix = Path(tree["archive"]).stem
    repository = next(
        record
        for record in manifest["repositories"]
        if prefix.startswith(Path(record["bundle"]).stem + "-worktree-")
    )
    support = [tree["index"], prefix + "-staged.patch", prefix + "-unstaged.patch"]
    if repository.get("shallow"):
        support.append(repository["shallow"])
    for name in support:
        if file_digest(archive_root / name) != manifest["support_files"][name]:
            raise ValueError(f"Support-file hash mismatch: {name}")
    for name, expected in [
        (repository["bundle"], repository["sha256"]),
        (tree["archive"], tree["sha256"]),
    ]:
        if file_digest(archive_root / name) != expected:
            raise ValueError(f"Archive hash mismatch: {name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    shallow = (
        archive_root / repository["shallow"] if repository.get("shallow") else None
    )
    restore_bundle(
        destination, (archive_root / repository["bundle"]).resolve(), shallow
    )
    subprocess.run(
        ["git", "-C", str(destination), "checkout", "--detach", tree["head"]],
        check=True,
        capture_output=True,
    )
    for kind, extra in [("staged", ["--index"]), ("unstaged", [])]:
        patch = archive_root / (prefix + "-" + kind + ".patch")
        if patch.stat().st_size:
            subprocess.run(
                ["git", "-C", str(destination), "apply", *extra, str(patch.resolve())],
                check=True,
                capture_output=True,
            )
    with tarfile.open(archive_root / tree["archive"]) as archive:
        for entry in tree["entries"]:
            relative = Path(entry["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or relative.parts[0] == ".git"
            ):
                raise ValueError("Unsafe recovery path")
            path = destination / relative
            if any(
                parent.is_symlink()
                for parent in path.parents
                if parent != destination.parent
            ):
                raise ValueError("Recovery path traverses a symlink")
            if path.is_symlink() or path.is_file():
                path.unlink()
            if entry["kind"] == "deleted":
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            member = archive.getmember(entry["path"])
            if entry["kind"] == "symlink":
                if not member.issym() or member.linkname != entry["target"]:
                    raise ValueError("Symlink mismatch")
                path.symlink_to(entry["target"])
            else:
                if not member.isfile():
                    raise ValueError("Expected regular file")
                with archive.extractfile(member) as incoming, path.open(
                    "wb"
                ) as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                path.chmod(entry["mode"])
                if file_digest(path) != entry["sha256"]:
                    raise ValueError("Recovered file hash mismatch")
    if git(destination, "status", "--porcelain=v1", "-z").hex() != tree["status_hex"]:
        raise ValueError("Recovered Git status differs")
    if (
        git(destination, "diff", "--cached", "--binary")
        != (archive_root / (prefix + "-staged.patch")).read_bytes()
    ):
        raise ValueError("Recovered staged state differs")
    return {
        "verified": True,
        "head": tree["head"],
        "files": len(tree["entries"]),
        "archive_sha256": tree["sha256"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["snapshot", "verify", "restore"])
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repository", type=Path, action="append", default=[])
    parser.add_argument("--artifact", type=Path, action="append", default=[])
    parser.add_argument("--source-worktree", type=Path)
    parser.add_argument("--restore-directory", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == "snapshot":
        if not args.repository:
            parser.error("snapshot requires at least one --repository")
        snapshot(args.destination.resolve(), args.repository, args.artifact)
    elif args.action == "restore":
        if not args.source_worktree or not args.restore_directory:
            parser.error("restore requires --source-worktree and --restore-directory")
        print(
            json.dumps(
                restore_worktree(
                    args.destination.resolve(),
                    args.source_worktree,
                    args.restore_directory.resolve(),
                )
            )
        )
    else:
        verify(args.destination.resolve())


if __name__ == "__main__":
    main()
