"""Create or resume one named App/Lakebase installation, then publish a gated release.

The private state directory is the installation's ownership journal. Unknown
resource collisions fail. There is no reset, adoption or deletion operation.
"""

import argparse
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("w") as stream:
        temporary.chmod(0o600)
        json.dump(value, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class Cli:
    def __init__(self, executable, profile, directory):
        if not profile:
            raise ValueError("Select a Databricks profile explicitly")
        self.executable, self.profile, self.directory = (
            str(executable),
            profile,
            directory,
        )
        probe = subprocess.check_output([self.executable, "version"], text=True)
        match = re.search(r"v(\d+)\.(\d+)\.(\d+)", probe)
        if not match or tuple(map(int, match.groups())) < (1, 0, 0):
            raise ValueError("Databricks CLI >=1.0.0 is required")

    def run(self, arguments, *, cwd=None):
        command = [
            self.executable,
            *arguments,
            "--profile",
            self.profile,
            "--output",
            "json",
        ]
        process = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
        log = self.directory / ("command-" + uuid.uuid4().hex + ".json")
        private_json(
            log,
            {
                "arguments": arguments,
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
            },
        )
        if process.returncode:
            raise RuntimeError(
                "Databricks command failed; inspect private receipt " + str(log)
            )
        if arguments[:2] in (["workspace", "import-dir"], ["workspace", "export-dir"]):
            # Directory operations emit a sequence of progress events, rather
            # than one JSON document. Their complete output is in the receipt;
            # publication verifies the transferred bytes separately.
            return {}
        return json.loads(process.stdout) if process.stdout.strip() else {}


def collection(value, key):
    return value if isinstance(value, list) else value.get(key, [])


def names(installation):
    if not re.fullmatch(r"[a-z](?:[a-z0-9-]{0,25}[a-z0-9])?", installation):
        raise ValueError(
            "Installation must start with a letter and fit the App's 30-character limit"
        )
    return "oc-" + installation


def bundle(state, *, database=None):
    resources = {
        "postgres_projects": {
            "state": {
                "project_id": state["project_id"],
                "display_name": state["marker"],
                "pg_version": 17,
                "lifecycle": {"prevent_destroy": True},
            }
        }
    }
    if database:
        bindings = [
            {
                "name": "postgres",
                "postgres": {
                    "branch": state["branch"],
                    "database": database,
                    "permission": "CAN_CONNECT_AND_CREATE",
                },
            }
        ]
        for key in ("extraction", "embedding", "grounding"):
            bindings.append(
                {
                    "name": key + "-model",
                    "serving_endpoint": {
                        "name": state[key + "_endpoint"],
                        "permission": "CAN_QUERY",
                    },
                }
            )
        if state.get("definition_volume"):
            bindings.append(
                {
                    "name": "workflow-packages",
                    "uc_securable": {
                        "securable_full_name": state["definition_volume"],
                        "securable_type": "VOLUME",
                        "permission": "READ_VOLUME",
                    },
                }
            )
        if state.get("docling_job_id") and state.get("docling_artifact_volume"):
            from docling_job_config import app_resources

            bindings.extend(
                app_resources(state["docling_job_id"], state["docling_artifact_volume"])
            )
        resources["apps"] = {
            "opencontracts": {
                "name": "${var.app_name}",
                "description": state["marker"],
                "source_code_path": ".",
                "resources": bindings,
            }
        }
    return {
        "bundle": {"name": state["app_name"]},
        "variables": {
            "app_name": {"default": "oc-${workspace.current_user.domain_friendly_name}"}
        },
        "workspace": {
            "root_path": "/Workspace/Users/${workspace.current_user.userName}/.opencontracts-installations/"
            + state["installation"]
            + "/bundle"
        },
        "sync": {"include": ["databricks.yml"]},
        "resources": resources,
        "targets": {
            "installation": {
                "mode": "production",
                "default": True,
                "variables": {"app_name": state["app_name"]},
            }
        },
    }


def write_bundle(directory, state, *, database=None):
    path = directory / "bundle"
    path.mkdir(exist_ok=True, mode=0o700)
    (path / "databricks.yml").write_text(
        yaml.safe_dump(bundle(state, database=database), sort_keys=False)
    )
    return path


def provision(args):
    directory = args.state_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    state_file = directory / "installation.json"
    cli = Cli(args.cli, args.profile, directory)
    profiles = cli.run(["auth", "profiles"])["profiles"]
    selected = next(profile for profile in profiles if profile["name"] == args.profile)
    if selected.get("valid") is not True:
        raise ValueError("Selected Databricks profile is not authenticated")
    host = selected["host"].rstrip("/")
    app_name = names(args.installation)
    apps = collection(cli.run(["apps", "list"]), "apps")
    projects = collection(cli.run(["postgres", "list-projects"]), "projects")
    current_app = next((a for a in apps if a["name"] == app_name), None)
    current_project = next(
        (p for p in projects if p["name"] == "projects/" + app_name), None
    )
    if state_file.exists():
        state = json.loads(state_file.read_text())
        expected = {
            "installation": args.installation,
            "host": host,
            "profile": args.profile,
            "app_name": app_name,
            "project_id": app_name,
        }
        if any(state.get(key) != value for key, value in expected.items()):
            raise ValueError(
                "Installation journal belongs to another name, profile or workspace"
            )
        if current_app and current_app.get("description") != state["marker"]:
            raise ValueError("App ownership marker differs; refusing to adopt it")
        if (
            current_project
            and (
                current_project.get("status", {}).get("display_name")
                or current_project.get("spec", {}).get("display_name")
            )
            != state["marker"]
        ):
            raise ValueError("Lakebase ownership marker differs; refusing to adopt it")
        if state.get("phase") == "provisioned" and (
            not current_app or not current_project
        ):
            raise ValueError(
                "Previously provisioned resources are missing; inspect recovery explicitly"
            )
    else:
        if current_app or current_project:
            raise ValueError(
                "Unknown resource name collision; choose a different installation"
            )
        state = {
            "installation": args.installation,
            "host": host,
            "profile": args.profile,
            "app_name": app_name,
            "project_id": app_name,
            "phase": "admitted",
            "marker": "OpenContracts installation "
            + args.installation
            + " "
            + uuid.uuid4().hex,
        }
    state.update(
        extraction_endpoint=args.extraction_endpoint,
        embedding_endpoint=args.embedding_endpoint,
        grounding_endpoint=args.grounding_endpoint,
        definition_volume=args.definition_volume,
    )
    private_json(state_file, state)
    path = write_bundle(directory, state, database=state.get("database"))
    resolved = cli.run(
        ["bundle", "validate", "--strict", "--target", "installation"], cwd=path
    )
    state["workspace_root"] = resolved["workspace"]["root_path"]
    private_json(state_file, state)
    cli.run(
        ["bundle", "deploy", "--target", "installation", "--auto-approve"], cwd=path
    )
    branches = collection(
        cli.run(["postgres", "list-branches", "projects/" + app_name]), "branches"
    )
    production = next(
        branch for branch in branches if branch["name"].endswith("/branches/production")
    )
    state["branch"] = production["name"]
    databases = collection(
        cli.run(["postgres", "list-databases", state["branch"]]), "databases"
    )
    database = next(
        db
        for db in databases
        if db.get("status", {}).get("postgres_database") == "databricks_postgres"
    )
    state["database"] = database["name"]
    private_json(state_file, state)
    path = write_bundle(directory, state, database=state["database"])
    resolved = cli.run(
        ["bundle", "validate", "--strict", "--target", "installation"], cwd=path
    )
    if resolved["resources"]["apps"]["opencontracts"]["name"] != app_name:
        raise ValueError("Resolved App name differs from installation identity")
    cli.run(
        ["bundle", "deploy", "--target", "installation", "--auto-approve"], cwd=path
    )
    app = cli.run(["apps", "get", app_name])
    state.update(phase="provisioned", app_url=app["url"], app_id=app["id"])
    private_json(state_file, state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "app_url": state["app_url"],
                "phase": state["phase"],
            }
        )
    )


def publish(args):
    directory = args.state_directory.resolve()
    state = json.loads((directory / "installation.json").read_text())
    if state["installation"] != args.installation or state["profile"] != args.profile:
        raise ValueError(
            "Publication must select the provisioned installation and profile"
        )
    cli = Cli(args.cli, args.profile, directory)
    release = args.release.resolve()
    config = yaml.safe_load((release / "app.yaml").read_text())
    environment = {item["name"]: item.get("value") for item in config["env"]}
    if environment.get("APP_ORIGIN") != state["app_url"].rstrip("/"):
        raise ValueError("Release origin belongs to another App")
    receipt = directory / ("publication-gate-" + uuid.uuid4().hex + ".json")
    subprocess.run(
        [
            str(args.python),
            str(ROOT / "tools/verify_staged_runtime.py"),
            "--release",
            str(release),
            "--python",
            str(args.python),
            "--receipt",
            str(args.receipt),
            "--output",
            str(receipt),
        ],
        check=True,
    )
    app = cli.run(["apps", "get", state["app_name"]])
    if app["id"] != state["app_id"] or app["description"] != state["marker"]:
        raise ValueError("App identity changed since provisioning")
    manifest = json.loads((release / "release.json").read_text())
    # A complete release inventory identifies configuration as well as archive bytes.
    import hashlib

    from verify_staged_runtime import inventory

    identity = hashlib.sha256(
        json.dumps(inventory(release), sort_keys=True).encode()
    ).hexdigest()
    workspace_path = (
        state["workspace_root"].removesuffix("/bundle") + "/releases/" + identity
    )
    cli.run(["workspace", "import-dir", str(release), workspace_path, "--overwrite"])
    # Check the uploaded bytes, including the launcher and resource configuration.
    # Local gates cannot detect a partial upload or notebook conversion.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="opencontracts-upload-check-") as temporary:
        downloaded = Path(temporary) / "release"
        cli.run(["workspace", "export-dir", workspace_path, str(downloaded)])
        if inventory(downloaded) != inventory(release):
            raise ValueError("Uploaded release differs from the locally gated files")
    # Revalidate immediately before the separately authorized deployment.
    adjacent = directory / ("deployment-gate-" + uuid.uuid4().hex + ".json")
    subprocess.run(
        [
            str(args.python),
            str(ROOT / "tools/verify_staged_runtime.py"),
            "--release",
            str(release),
            "--python",
            str(args.python),
            "--receipt",
            str(args.receipt),
            "--output",
            str(adjacent),
        ],
        check=True,
    )
    if app.get("compute_status", {}).get("state") != "ACTIVE":
        cli.run(["apps", "start", state["app_name"]])
    deployment = cli.run(
        [
            "apps",
            "deploy",
            state["app_name"],
            "--source-code-path",
            workspace_path,
            "--mode",
            "SNAPSHOT",
        ]
    )
    state.update(
        deployment=deployment,
        release_identity=identity,
        archive_sha256=manifest["archive_sha256"],
        workspace_release=workspace_path,
    )
    private_json(directory / "installation.json", state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "app_url": state["app_url"],
                "release_identity": identity,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--installation", required=True)
    parser.add_argument("--state-directory", type=Path, required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("provision")
    create.add_argument("--extraction-endpoint", required=True)
    create.add_argument("--embedding-endpoint", required=True)
    create.add_argument("--grounding-endpoint", default="databricks-gpt-oss-120b")
    create.add_argument("--definition-volume", required=True)
    create.set_defaults(run=provision)
    deploy = commands.add_parser("publish")
    deploy.add_argument("--release", type=Path, required=True)
    deploy.add_argument("--receipt", type=Path, required=True)
    deploy.add_argument("--python", type=Path, required=True)
    deploy.set_defaults(run=publish)
    args = parser.parse_args()
    os.umask(0o077)
    import fcntl

    args.state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_directory / "installation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        args.run(args)


if __name__ == "__main__":
    main()
