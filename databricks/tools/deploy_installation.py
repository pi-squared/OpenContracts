"""Create or resume one named App/Lakebase installation, then publish a gated release.

The private state directory is the installation's ownership journal. Unknown
resource collisions fail. There is no reset, adoption or deletion operation.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import yaml

if __package__:
    from .database_privileges import privilege_gaps
    from .installation_configuration import validate_configuration
else:
    from database_privileges import privilege_gaps
    from installation_configuration import validate_configuration

ROOT = Path(__file__).resolve().parents[1]
APP_CREATION_TIMEOUT_SECONDS = 120
APP_CREATION_POLL_SECONDS = 2


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

    def run(self, arguments, *, cwd=None, timeout=None):
        command = [
            self.executable,
            *arguments,
            "--profile",
            self.profile,
            "--output",
            "json",
        ]
        process = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
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
    if getattr(args, "existing_profile", None):
        return provision_existing(args)
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


def installation_profile(path):
    """Read explicit retained-resource selection; never infer a database."""
    value = json.loads(path.read_text())
    if value.get("format") != "opencontracts-existing-installation.v1":
        raise ValueError("Unsupported existing installation profile")
    lakebase = value["lakebase"]
    branch, database = lakebase["branch"], lakebase["database"]
    if not re.fullmatch(r"projects/[a-z0-9-]+/branches/[a-z0-9-]+", branch):
        raise ValueError("Select an exact Lakebase branch")
    if not database.startswith(branch + "/databases/") or not re.fullmatch(
        r"[a-z][a-z0-9_]{0,62}", lakebase["schema"]
    ):
        raise ValueError("Select an exact database and PostgreSQL schema")
    resources = value["source_app"]["resources"]
    bindings = {entry["name"]: entry for entry in resources}
    if len(bindings) != len(resources) or (
        bindings["postgres"]["postgres"]["branch"] != branch
        or bindings["postgres"]["postgres"]["database"] != database
    ):
        raise ValueError("Existing resource bindings disagree with selected Lakebase")
    if value["git_repository"] != {
        "url": "https://github.com/pi-squared/OpenContracts.git",
        "provider": "gitHub",
    }:
        raise ValueError(
            "Testing promotion must select the canonical OpenContracts fork"
        )
    validate_configuration(value["runtime_configuration"], require_origin=False)
    if value["runtime_configuration"]["OPENCONTRACTS_SCHEMA"] != lakebase["schema"]:
        raise ValueError("Runtime configuration disagrees with the selected schema")
    return value


def selected_workspace(cli, profile):
    profiles = cli.run(["auth", "profiles"])["profiles"]
    selected = next((item for item in profiles if item["name"] == profile), None)
    if not selected or selected.get("valid") is not True:
        raise ValueError("Selected Databricks profile is not authenticated")
    return selected["host"].rstrip("/")


def wait_for_created_app(cli, state, directory, expected_resources, initial_app):
    """Wait only for the already owned creation identity; never start compute."""
    deadline = time.monotonic() + APP_CREATION_TIMEOUT_SECONDS
    expected_bindings = {entry["name"]: entry for entry in expected_resources}
    app = initial_app
    is_readback = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(
                "New App readiness timed out; resume the owned pending creation"
            )
        if app is None:
            try:
                app = cli.run(["apps", "get", state["app_name"]], timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise ValueError(
                    "New App readiness timed out; resume the owned pending creation"
                ) from error
            is_readback = True
        if (
            app.get("name") != state["app_name"]
            or app.get("id") != state["app_creation_id"]
        ):
            raise ValueError("App identity changed during creation")
        if app.get("description") != state["marker"]:
            raise ValueError("App ownership marker changed during creation")
        compute = (app.get("compute_status") or {}).get("state")
        if compute not in (None, "STARTING", "STOPPING", "STOPPED"):
            raise ValueError("New App has unexpected compute state")
        if (app.get("app_status") or {}).get("state") in (
            "ERROR",
            "FAILED",
            "CRASHED",
            "RUNNING",
        ) or app.get("active_deployment"):
            raise ValueError("New App has unexpected deployment or error state")
        repository = app.get("git_repository") or {}
        if repository.get("auto_deploy") or any(
            repository.get(key) not in (None, value)
            for key, value in state["git_repository"].items()
        ):
            raise ValueError("App Git repository changed during creation")
        repository_ready = all(
            repository.get(key) == value
            for key, value in state["git_repository"].items()
        )
        resources = app.get("resources")
        if resources is not None:
            if (
                not isinstance(resources, list)
                or any(
                    not isinstance(entry, dict)
                    or entry != expected_bindings.get(entry.get("name"))
                    for entry in resources
                )
                or len({entry["name"] for entry in resources}) != len(resources)
            ):
                raise ValueError("App resource bindings changed during creation")
        resources_ready = resources is not None and len(resources) == len(
            expected_resources
        )
        changed = False
        for key, observed in (
            ("app_creation_url", app.get("url")),
            ("app_creation_principal", app.get("service_principal_client_id")),
        ):
            if observed:
                if state.get(key) and state[key] != observed:
                    raise ValueError("App identity changed during creation")
                if not state.get(key):
                    state[key] = observed
                    changed = True
        if changed:
            private_json(directory / "installation.json", state)
        if (
            is_readback
            and compute == "STOPPED"
            and app.get("url")
            and app.get("service_principal_client_id")
            and repository_ready
            and resources_ready
        ):
            return app
        if is_readback:
            time.sleep(
                min(APP_CREATION_POLL_SECONDS, max(0, deadline - time.monotonic()))
            )
        app = None


def provision_existing(args):
    directory = args.state_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    config = installation_profile(args.existing_profile.resolve())
    profile_hash = hashlib.sha256(args.existing_profile.read_bytes()).hexdigest()
    cli = Cli(args.cli, args.profile, directory)
    host = selected_workspace(cli, args.profile)
    app_name = names(args.installation)
    source = cli.run(["apps", "get", config["source_app"]["name"]])
    if (
        source["id"] != config["source_app"]["id"]
        or source["resources"] != config["source_app"]["resources"]
    ):
        raise ValueError("Selected source App identity or resource bindings changed")
    lakebase = config["lakebase"]
    cli.run(["postgres", "get-branch", lakebase["branch"]])
    database = cli.run(["postgres", "get-database", lakebase["database"]])
    if database["name"] != lakebase["database"]:
        raise ValueError("Selected Lakebase database identity differs")
    current = next(
        (
            item
            for item in collection(cli.run(["apps", "list"]), "apps")
            if item["name"] == app_name
        ),
        None,
    )
    state_file = directory / "installation.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        expected = {
            "installation": args.installation,
            "host": host,
            "profile": args.profile,
            "app_name": app_name,
            "database_mode": "existing",
            "selection_sha256": profile_hash,
        }
        if any(state.get(key) != value for key, value in expected.items()):
            raise ValueError("Existing installation selection differs from its journal")
        if current and current.get("description") != state["marker"]:
            raise ValueError("App ownership marker differs; refusing to adopt it")
        if (
            state.get("phase") in ("provisioned", "configured")
            or state.get("app_creation_id")
        ) and not current:
            raise ValueError(
                "Previously provisioned App is missing; inspect recovery explicitly"
            )
    else:
        if current:
            raise ValueError(
                "Unknown App name collision; choose a different installation"
            )
        state = {
            "installation": args.installation,
            "host": host,
            "profile": args.profile,
            "app_name": app_name,
            "database_mode": "existing",
            "selection_sha256": profile_hash,
            "branch": lakebase["branch"],
            "database": lakebase["database"],
            "schema": lakebase["schema"],
            "postgres_database": database["status"]["postgres_database"],
            "source_app": config["source_app"],
            "git_repository": config["git_repository"],
            "configuration_secret": config["configuration_secret"],
            "runtime_configuration": config["runtime_configuration"],
            "phase": "admitted",
            "marker": "OpenContracts installation "
            + args.installation
            + " "
            + uuid.uuid4().hex,
        }
    private_json(state_file, state)
    if current is None:
        body = directory / ("create-app-" + uuid.uuid4().hex + ".json")
        private_json(
            body,
            {
                "name": app_name,
                "description": state["marker"],
                "resources": [
                    entry
                    for entry in config["source_app"]["resources"]
                    if entry["name"] != "docling-job"
                ],
                "git_repository": config["git_repository"],
            },
        )
        current = cli.run(
            ["apps", "create", "--no-compute", "--no-wait", "--json", "@" + str(body)]
        )
    if not state.get("app_id"):
        if (
            current.get("name") != app_name
            or current.get("description") != state["marker"]
        ):
            raise ValueError("App ownership marker differs; refusing to adopt it")
        creation_id = current.get("id")
        if not creation_id or state.get("app_creation_id", creation_id) != creation_id:
            raise ValueError("App identity changed during creation")
        state["app_creation_id"] = creation_id
        private_json(state_file, state)
        expected_resources = [
            entry
            for entry in config["source_app"]["resources"]
            if entry["name"] != "docling-job"
        ]
        app = wait_for_created_app(cli, state, directory, expected_resources, current)
    else:
        app = cli.run(["apps", "get", app_name])
    if app.get("description") != state["marker"]:
        raise ValueError("Provisioned App ownership marker differs")
    if state.get("app_id") and state["app_id"] != app["id"]:
        raise ValueError("App identity changed since provisioning")
    if state.get("app_id"):
        check_app(state, app)
    state.update(
        phase="provisioned",
        app_url=app["url"],
        app_id=app["id"],
        service_principal_client_id=app["service_principal_client_id"],
        resources=app["resources"],
    )
    private_json(state_file, state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "phase": state["phase"],
                "database_mode": "existing",
            }
        )
    )


def bound_installation(args):
    directory = args.state_directory.resolve()
    state = json.loads((directory / "installation.json").read_text())
    if state["installation"] != args.installation or state["profile"] != args.profile:
        raise ValueError("Select the journal's installation and workspace profile")
    return directory, state, Cli(args.cli, args.profile, directory)


def check_app(state, app):
    if (
        app["id"] != state["app_id"]
        or app["description"] != state["marker"]
        or app["url"] != state["app_url"]
    ):
        raise ValueError("App identity changed since provisioning")
    if app.get("resources") != state["resources"]:
        raise ValueError("App resource bindings changed since configuration")
    repository = app.get("git_repository", {})
    if any(
        repository.get(key) != value for key, value in state["git_repository"].items()
    ) or repository.get("auto_deploy"):
        raise ValueError("App Git repository or deployment mode differs")


def authorize_existing(args):
    """Grant direct retained-state access; never delegate its managed owner role."""
    directory, state, cli = bound_installation(args)
    config = installation_profile(args.existing_profile.resolve())
    if (
        hashlib.sha256(args.existing_profile.read_bytes()).hexdigest()
        != state["selection_sha256"]
    ):
        raise ValueError("Existing installation profile changed")
    app = cli.run(["apps", "get", state["app_name"]])
    check_app(state, app)
    state.update(
        database_permissions_verified=False,
        database_permission_mode="existing-direct-pending",
        owner_role_membership_claimed=False,
    )
    private_json(directory / "installation.json", state)
    import psycopg2
    from databricks.sdk import WorkspaceClient
    from psycopg2 import sql

    client = WorkspaceClient(profile=args.profile)
    if client.config.host.rstrip("/") != state["host"]:
        raise ValueError("Permission operation selected another workspace")
    lakebase = config["lakebase"]
    endpoint = client.postgres.get_endpoint(name=lakebase["endpoint"])
    if not endpoint.name.startswith(state["branch"] + "/endpoints/"):
        raise ValueError("Permission endpoint differs from retained branch")
    database = client.postgres.get_database(name=state["database"])
    credential = client.postgres.generate_database_credential(endpoint=endpoint.name)
    username = client.current_user.me().user_name
    owner = lakebase["schema_owner_role"]
    if owner != config["source_app"]["service_principal_client_id"]:
        raise ValueError(
            "Existing schema owner must be the explicitly selected source App role"
        )
    principal = state["service_principal_client_id"]
    with psycopg2.connect(
        host=endpoint.status.hosts.host,
        dbname=database.status.postgres_database,
        user=username,
        password=credential.token,
        sslmode="require",
        connect_timeout=30,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s",
                (state["schema"],),
            )
            row = cursor.fetchone()
            if not row or row[0] != owner:
                raise ValueError(
                    "Retained schema ownership differs; no ownership is changed"
                )
            cursor.execute(
                "SELECT DISTINCT pg_get_userbyid(c.relowner) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind IN ('r','p','S')",
                (state["schema"],),
            )
            if any(row[0] != owner for row in cursor.fetchall()):
                raise ValueError(
                    "Retained relations have unexpected owners; inspect permissions explicitly"
                )
            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", (principal,)
            )
            if not cursor.fetchone()[0]:
                raise ValueError("New App database role is not provisioned")
            cursor.execute(
                "SELECT c.relname,c.relkind,pg_get_userbyid(c.relowner) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind IN ('r','p','S') ORDER BY c.relname",
                (state["schema"],),
            )
            retained_relations = cursor.fetchall()
            cursor.execute(
                "SELECT to_regclass(%s)", (state["schema"] + ".django_migrations",)
            )
            if not cursor.fetchone()[0]:
                raise ValueError(
                    "Retained migration state is missing; the owner must initialize it separately"
                )
            migration_query = sql.SQL(
                "SELECT app,name FROM {}.django_migrations ORDER BY app,name"
            ).format(sql.Identifier(state["schema"]))
            cursor.execute(migration_query)
            retained_migrations = cursor.fetchall()
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(state["schema"]), sql.Identifier(principal)
                )
            )
            cursor.execute(
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO {}"
                ).format(sql.Identifier(state["schema"]), sql.Identifier(principal))
            )
            sequence_requirement = (
                "Retained owner must grant USAGE and SELECT on all retained sequences "
                "to the new App role; authorization transaction rolled back"
            )
            gaps = privilege_gaps(cursor, state["schema"], role=principal)
            if gaps["sequences"]:
                try:
                    cursor.execute(
                        sql.SQL(
                            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}"
                        ).format(
                            sql.Identifier(state["schema"]), sql.Identifier(principal)
                        )
                    )
                except psycopg2.errors.InsufficientPrivilege as error:
                    raise ValueError(sequence_requirement) from error
            gaps = privilege_gaps(cursor, state["schema"], role=principal)
            if gaps["schema"]:
                raise ValueError("New App schema USAGE is unavailable")
            if gaps["tables"]:
                raise ValueError(
                    "New App retained table CRUD permissions are unavailable"
                )
            if gaps["sequences"]:
                raise ValueError(sequence_requirement)
            cursor.execute(
                "SELECT c.relname,c.relkind,pg_get_userbyid(c.relowner) FROM pg_class c "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind IN ('r','p','S') ORDER BY c.relname",
                (state["schema"],),
            )
            if cursor.fetchall() != retained_relations:
                raise ValueError(
                    "Retained relation ownership/state changed during authorization"
                )
            cursor.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s",
                (state["schema"],),
            )
            if cursor.fetchone() != (owner,):
                raise ValueError(
                    "Retained schema ownership changed during authorization"
                )
            cursor.execute(migration_query)
            if cursor.fetchall() != retained_migrations:
                raise ValueError(
                    "Retained migration state changed during authorization"
                )
    state.update(
        database_permissions_verified=True,
        retained_owner_role=owner,
        database_permission_mode="existing-direct",
        owner_role_membership_claimed=False,
        retained_relation_count=len(retained_relations),
        retained_migration_count=len(retained_migrations),
        retained_relations_sha256=hashlib.sha256(
            json.dumps(retained_relations).encode()
        ).hexdigest(),
        retained_migrations_sha256=hashlib.sha256(
            json.dumps(retained_migrations).encode()
        ).hexdigest(),
        ownership_transferred=False,
    )
    private_json(directory / "installation.json", state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "database_permissions_verified": True,
                "ownership_transferred": False,
            }
        )
    )


def secret_metadata(cli, state):
    selected = state["configuration_secret"]
    secrets = collection(
        cli.run(["secrets", "list-secrets", selected["scope"]]), "secrets"
    )
    return next((item for item in secrets if item["key"] == selected["key"]), None)


def verify_docling_files(cli, workspace, source_files):
    for name, source in source_files.items():
        exported = cli.run(
            ["workspace", "export", workspace + "/" + name, "--format", "SOURCE"]
        )
        if base64.b64decode(exported["content"], validate=True) != source.read_bytes():
            raise ValueError("Uploaded source-bound Docling bytes differ")


def configure_existing(args):
    directory, state, cli = bound_installation(args)
    config = installation_profile(args.existing_profile.resolve())
    if (
        hashlib.sha256(args.existing_profile.read_bytes()).hexdigest()
        != state["selection_sha256"]
    ):
        raise ValueError("Existing installation profile changed")
    app = cli.run(["apps", "get", state["app_name"]])
    check_app(state, app)
    settings = validate_configuration(
        {
            **state["runtime_configuration"],
            "APP_ORIGIN": state["app_url"].rstrip("/"),
            "OPENCONTRACTS_DATABASE_MODE": "existing",
        }
    )
    encoded = json.dumps(settings, sort_keys=True)
    secret = state["configuration_secret"]
    scopes = collection(cli.run(["secrets", "list-scopes"]), "scopes")
    exists = any(item["name"] == secret["scope"] for item in scopes)
    if exists and not state.get("configuration_scope_created"):
        raise ValueError(
            "Unknown configuration scope collision; refusing to overwrite it"
        )
    if not exists:
        if state.get("configuration_scope_created"):
            raise ValueError("Previously created configuration scope is missing")
        cli.run(["secrets", "create-scope", secret["scope"]])
        state["configuration_scope_created"] = True
        private_json(directory / "installation.json", state)
    metadata = secret_metadata(cli, state)
    if state.get("configuration_secret_metadata"):
        if (
            metadata != state["configuration_secret_metadata"]
            or hashlib.sha256(encoded.encode()).hexdigest()
            != state["configuration_sha256"]
        ):
            raise ValueError(
                "Bound installation configuration changed; inspect it explicitly"
            )
    else:
        if metadata:
            raise ValueError("Unknown configuration key collision")
        body = directory / ("configuration-secret-" + uuid.uuid4().hex + ".json")
        private_json(
            body,
            {"scope": secret["scope"], "key": secret["key"], "string_value": encoded},
        )
        cli.run(
            [
                "secrets",
                "put-secret",
                "--json",
                "@" + str(body),
            ]
        )
        metadata = secret_metadata(cli, state)
        if not metadata:
            raise ValueError("Configuration key was not confirmed")
        state.update(
            configuration_secret_metadata=metadata,
            configuration_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        )
        private_json(directory / "installation.json", state)
    resources = [
        entry
        for entry in config["source_app"]["resources"]
        if entry["name"] != "docling-job"
    ]
    if config.get("docling"):
        job = config["docling"]
        source_files = {
            "docling_pdf_job.py": ROOT / "jobs/docling_pdf_job.py",
            "parser_exports.py": ROOT / "port/python/databricks_port/parser_exports.py",
        }
        identity = hashlib.sha256(
            json.dumps(
                {
                    name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for name, path in source_files.items()
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        workspace = (
            "/Workspace/Shared/.opencontracts-installations/"
            + state["installation"]
            + "/docling/"
            + identity
        )
        if __package__:
            from .docling_job_config import job_settings, job_settings_match
        else:
            from docling_job_config import job_settings, job_settings_match
        expected = job_settings(
            state["app_name"], workspace, job["run_as_principal"], job["rapidocr_wheel"]
        )
        expected["tags"]["installation_owner"] = state["marker"]
        if state.get("docling_job_id"):
            if state.get("docling_job_settings") != expected:
                raise ValueError(
                    "Owned Docling source/settings changed; inspect the new revision explicitly"
                )
            verify_docling_files(cli, workspace, source_files)
        else:
            found = collection(
                cli.run(["jobs", "list", "--name", expected["name"]]), "jobs"
            )
            if found:
                raise ValueError("Unknown Docling job name collision")
            cli.run(["workspace", "mkdirs", workspace])
            for name, source in source_files.items():
                cli.run(
                    [
                        "workspace",
                        "import",
                        workspace + "/" + name,
                        "--format",
                        "RAW",
                        "--file",
                        str(source),
                    ]
                )
            verify_docling_files(cli, workspace, source_files)
            body = directory / ("create-docling-job-" + uuid.uuid4().hex + ".json")
            private_json(body, expected)
            created = cli.run(["jobs", "create", "--json", "@" + str(body)])
            state.update(
                docling_job_id=created["job_id"],
                docling_job_settings=expected,
                docling_source_sha256=identity,
            )
            private_json(directory / "installation.json", state)
        observed = cli.run(["jobs", "get", str(state["docling_job_id"])])["settings"]
        if not job_settings_match(expected, observed):
            raise ValueError("Owned Docling job settings differ from their journal")
        resources.append(
            {
                "name": "docling-job",
                "job": {
                    "id": str(state["docling_job_id"]),
                    "permission": "CAN_MANAGE_RUN",
                },
            }
        )
    resources.append(
        {"name": "installation-config", "secret": {**secret, "permission": "READ"}}
    )
    if resources != state["resources"]:
        body = directory / ("configure-app-" + uuid.uuid4().hex + ".json")
        private_json(
            body, {"app": {"resources": resources}, "update_mask": "resources"}
        )
        cli.run(
            [
                "apps",
                "create-update",
                state["app_name"],
                "--json",
                "@" + str(body),
            ]
        )
        updated = cli.run(["apps", "get", state["app_name"]])
        if updated["id"] != state["app_id"] or updated["resources"] != resources:
            raise ValueError("Updated App resources differ")
        state["resources"] = resources
    state["phase"] = "configured"
    private_json(directory / "installation.json", state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "phase": "configured",
                "resource_count": len(resources),
                "configured_workflow_hashes": len(
                    json.loads(settings["WORKFLOW_INSTALL_HASHES"])
                ),
            }
        )
    )


def publish_git(args):
    directory, state, cli = bound_installation(args)
    if (
        state.get("phase") != "configured"
        or state.get("database_permissions_verified") is not True
    ):
        raise ValueError(
            "Git publication needs verified existing database permissions and configuration"
        )
    if __package__:
        from .release_promotion import (
            APP_PATH,
            CANONICAL_REPOSITORY,
            PROMOTION_PATH,
            clean_head,
            git,
            remote_head,
            source_inventory,
            validated_release,
        )
        from .verify_staged_runtime import inventory
    else:
        from release_promotion import (
            APP_PATH,
            CANONICAL_REPOSITORY,
            PROMOTION_PATH,
            clean_head,
            git,
            remote_head,
            source_inventory,
            validated_release,
        )
        from verify_staged_runtime import inventory
    promotion = json.loads(args.promotion_receipt.read_text())
    if (
        promotion.get("published") is not True
        or promotion.get("remote_exact") is not True
    ):
        raise ValueError("Promotion receipt does not establish Git publication")
    checkout = args.git_checkout.resolve()
    head, record = promotion["head"], promotion["promotion"]
    rollback = getattr(args, "rollback", False)
    expected_remote = args.expected_remote_commit if rollback else head
    if (
        git(checkout, "rev-parse", "HEAD") != head
        or git(checkout, "status", "--porcelain", "--untracked-files=all")
        or git(checkout, "config", "--get", "remote.origin.url") != CANONICAL_REPOSITORY
        or remote_head(checkout, record["testing_branch"]) != expected_remote
        or git(checkout, "rev-parse", "HEAD^{tree}") != promotion.get("tree")
        or json.loads((checkout / PROMOTION_PATH).read_text()) != record
        or source_inventory(checkout, head) != record["source_files"]
    ):
        raise ValueError("Published testing source moved")
    if rollback:
        # The operator pins a freshly inspected current tip. Only a previously
        # promoted ancestor of that exact testing history is eligible.
        git(checkout, "merge-base", "--is-ancestor", head, expected_remote)
    release = args.release.resolve()
    verification_source = args.verification_source.resolve()
    verification_checkout = verification_source.parent
    if (
        verification_source.name != "databricks"
        or clean_head(verification_checkout) not in (record["development_commit"], head)
        or source_inventory(verification_checkout, "HEAD") != record["source_files"]
    ):
        raise ValueError(
            "Selected historical verification source differs from promotion"
        )
    validated_release(
        release, args.python, args.receipt.resolve(), source_root=verification_source
    )
    if (
        inventory(release) != record["release_files"]
        or inventory(checkout / APP_PATH) != record["release_files"]
    ):
        raise ValueError("Git runtime differs from the exact gated release")
    app = cli.run(["apps", "get", state["app_name"]])
    check_app(state, app)
    if secret_metadata(cli, state) != state["configuration_secret_metadata"]:
        raise ValueError("Bound installation configuration changed before deployment")
    if remote_head(checkout, record["testing_branch"]) != expected_remote:
        raise ValueError("Testing remote moved adjacent to Git deployment")
    if app.get("compute_status", {}).get("state") != "ACTIVE":
        cli.run(["apps", "start", state["app_name"]])
    deployment = cli.run(
        [
            "apps",
            "deploy",
            state["app_name"],
            "--git-commit",
            head,
            "--git-source-code-path",
            APP_PATH,
        ]
    )
    if deployment.get("status", {}).get("state") != "SUCCEEDED":
        raise ValueError("Git deployment did not succeed")
    final = cli.run(["apps", "get", state["app_name"]])
    check_app(state, final)
    actual = final["active_deployment"].get("git_source", {})
    if (
        actual.get("resolved_commit") != head
        or actual.get("source_code_path") != APP_PATH
        or final.get("app_status", {}).get("state") != "RUNNING"
    ):
        raise ValueError("Running App does not establish the expected Git source")
    if remote_head(checkout, record["testing_branch"]) != expected_remote:
        raise ValueError("Testing remote moved during Git deployment")
    state.update(
        deployment=deployment,
        git_commit=head,
        git_source_code_path=APP_PATH,
        archive_sha256=record["archive_sha256"],
        recipe_sha256=record["recipe_sha256"],
    )
    private_json(directory / "installation.json", state)
    print(
        json.dumps(
            {
                "installation": args.installation,
                "git_commit": head,
                "source_code_path": APP_PATH,
                "running": True,
                "rollback": rollback,
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
    create.add_argument("--existing-profile", type=Path)
    create.add_argument("--extraction-endpoint")
    create.add_argument("--embedding-endpoint")
    create.add_argument("--grounding-endpoint", default="databricks-gpt-oss-120b")
    create.add_argument("--definition-volume")
    create.set_defaults(run=provision)
    deploy = commands.add_parser("publish")
    deploy.add_argument("--release", type=Path, required=True)
    deploy.add_argument("--receipt", type=Path, required=True)
    deploy.add_argument("--python", type=Path, required=True)
    deploy.set_defaults(run=publish)
    authorize = commands.add_parser("authorize-existing")
    authorize.add_argument("--existing-profile", type=Path, required=True)
    authorize.set_defaults(run=authorize_existing)
    configure = commands.add_parser("configure-existing")
    configure.add_argument("--existing-profile", type=Path, required=True)
    configure.set_defaults(run=configure_existing)
    git_source_arguments = argparse.ArgumentParser(add_help=False)
    git_source_arguments.add_argument("--release", type=Path, required=True)
    git_source_arguments.add_argument("--receipt", type=Path, required=True)
    git_source_arguments.add_argument("--python", type=Path, required=True)
    git_source_arguments.add_argument("--promotion-receipt", type=Path, required=True)
    git_source_arguments.add_argument("--git-checkout", type=Path, required=True)
    git_source_arguments.add_argument("--verification-source", type=Path, required=True)
    git_deploy = commands.add_parser("publish-git", parents=[git_source_arguments])
    git_deploy.set_defaults(run=publish_git, rollback=False)
    rollback = commands.add_parser("rollback-git", parents=[git_source_arguments])
    rollback.add_argument("--expected-remote-commit", required=True)
    rollback.set_defaults(run=publish_git, rollback=True)
    args = parser.parse_args()
    if (
        args.command == "provision"
        and not args.existing_profile
        and not all(
            (args.extraction_endpoint, args.embedding_endpoint, args.definition_volume)
        )
    ):
        parser.error(
            "Fresh provisioning requires explicit extraction, embedding and definition resources"
        )
    os.umask(0o077)
    import fcntl

    args.state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (args.state_directory / "installation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        args.run(args)


if __name__ == "__main__":
    main()
