"""Existing-state installation is explicit and does not manage the database."""

import base64
import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import deploy_installation as deployment


class ExistingLakebaseTests(unittest.TestCase):
    def test_new_app_references_selected_database_without_provisioning_lakebase(self):
        branch = "projects/existing/branches/production"
        database = branch + "/databases/db"
        fresh = {
            "name": "oc-source",
            "id": "source-app",
            "resources": [
                {
                    "name": "postgres",
                    "postgres": {
                        "branch": branch,
                        "database": database,
                        "permission": "CAN_CONNECT_AND_CREATE",
                    },
                }
            ],
        }
        calls = []
        apps = [fresh]

        class FakeCli:
            def __init__(self, *args):
                pass

            def run(self, args, **kwargs):
                calls.append(args)
                if args == ["auth", "profiles"]:
                    return {
                        "profiles": [
                            {
                                "name": "chosen",
                                "host": "https://workspace.invalid",
                                "valid": True,
                            }
                        ]
                    }
                if args == ["apps", "list"]:
                    return apps
                if args == ["apps", "get", "oc-source"]:
                    return fresh
                if args[:2] == ["postgres", "get-database"]:
                    return {
                        "name": database,
                        "status": {"postgres_database": "databricks_postgres"},
                    }
                if args[:2] == ["postgres", "get-branch"]:
                    return {"name": branch, "status": {"state": "READY"}}
                if args[:2] == ["apps", "create"]:
                    assert args[2:] == ["--no-compute", "--no-wait", "--json", args[-1]]
                    body = json.loads(
                        Path(args[args.index("--json") + 1][1:]).read_text()
                    )
                    app = {
                        **body,
                        "name": body["name"],
                        "id": "new-app",
                        "url": "https://new.invalid",
                        "service_principal_client_id": "new-principal",
                        "compute_status": {"state": "STOPPED"},
                    }
                    apps.append(app)
                    return app
                if args == ["apps", "get", "oc-testing-fixture"]:
                    return apps[-1]
                raise AssertionError(args)

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            deployment, "Cli", FakeCli
        ):
            root = Path(temporary)
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "format": "opencontracts-existing-installation.v1",
                        "source_app": {
                            "name": "oc-source",
                            "id": "source-app",
                            "resources": fresh["resources"],
                        },
                        "lakebase": {
                            "branch": branch,
                            "database": database,
                            "schema": "opencontracts",
                        },
                        "git_repository": {
                            "url": "https://github.com/pi-squared/OpenContracts.git",
                            "provider": "gitHub",
                        },
                        "configuration_secret": {"scope": "fixture", "key": "runtime"},
                        "runtime_configuration": {
                            "OPENCONTRACTS_SCHEMA": "opencontracts",
                            "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/workflow-packages",
                            "WORKFLOW_INSTALL_HASHES": "[]",
                            "PILOT_USERNAME": "pilot-owner",
                        },
                    }
                )
            )
            args = SimpleNamespace(
                state_directory=root / "state",
                cli=Path("/unused"),
                profile="chosen",
                installation="testing-fixture",
                existing_profile=profile,
            )
            deployment.provision(args)
            state = json.loads((args.state_directory / "installation.json").read_text())
            self.assertEqual(state["database"], database)
            self.assertEqual(state["database_mode"], "existing")
            self.assertEqual(apps[-1]["resources"], fresh["resources"])
            creation = next(args for args in calls if args[:2] == ["apps", "create"])
            self.assertIn("--no-compute", creation)
            self.assertIn("--no-wait", creation)
            self.assertNotIn("no_compute", apps[-1])
            self.assertEqual(apps[-1]["compute_status"]["state"], "STOPPED")
            self.assertEqual(
                apps[-1]["git_repository"]["url"],
                "https://github.com/pi-squared/OpenContracts.git",
            )
            deployment.provision(args)
            repeated = json.loads(
                (args.state_directory / "installation.json").read_text()
            )
            self.assertEqual(repeated["app_id"], "new-app")
            self.assertEqual(
                sum(arguments[:2] == ["apps", "create"] for arguments in calls), 1
            )
            apps[-1]["resources"] = []
            with self.assertRaisesRegex(ValueError, "resource bindings changed"):
                deployment.provision(args)
        self.assertFalse(
            any(
                args[0] == "bundle" or args[:2] == ["postgres", "create-project"]
                for args in calls
            )
        )

    def test_repeat_configuration_rejects_changed_owned_parser_bytes_before_app_updates(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile.json"
            resources = [
                {
                    "name": "postgres",
                    "postgres": {
                        "branch": "projects/existing/branches/production",
                        "database": "projects/existing/branches/production/databases/db",
                        "permission": "CAN_CONNECT_AND_CREATE",
                    },
                }
            ]
            configuration = {
                "OPENCONTRACTS_SCHEMA": "opencontracts",
                "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/workflow-packages",
                "WORKFLOW_INSTALL_HASHES": "[]",
                "PILOT_USERNAME": "pilot-owner",
            }
            repository = {
                "url": "https://github.com/pi-squared/OpenContracts.git",
                "provider": "gitHub",
            }
            profile.write_text(
                json.dumps(
                    {
                        "format": "opencontracts-existing-installation.v1",
                        "source_app": {
                            "name": "oc-source",
                            "id": "source-app",
                            "resources": resources,
                        },
                        "lakebase": {
                            "branch": "projects/existing/branches/production",
                            "database": "projects/existing/branches/production/databases/db",
                            "schema": "opencontracts",
                        },
                        "git_repository": repository,
                        "configuration_secret": {"scope": "fixture", "key": "runtime"},
                        "runtime_configuration": configuration,
                        "docling": {
                            "run_as_principal": "chosen-principal",
                            "rapidocr_wheel": "/Volumes/c/s/v/rapidocr.whl",
                            "artifact_volume": "c.s.v",
                        },
                    }
                )
            )
            directory = root / "state"
            deployment.private_json(
                directory / "installation.json",
                {
                    "installation": "fixture",
                    "profile": "chosen",
                    "app_name": "oc-fixture",
                    "app_id": "new-app",
                    "marker": "owned",
                    "app_url": "https://new.invalid",
                    "resources": resources,
                    "git_repository": repository,
                    "runtime_configuration": configuration,
                    "configuration_secret": {"scope": "fixture", "key": "runtime"},
                    "selection_sha256": hashlib.sha256(
                        profile.read_bytes()
                    ).hexdigest(),
                    "database_permissions_verified": False,
                },
            )
            app = {
                "id": "new-app",
                "description": "owned",
                "url": "https://new.invalid",
                "resources": resources,
                "git_repository": repository,
            }
            external = {
                "scopes": [],
                "metadata": [],
                "files": {},
                "settings": None,
                "job_creations": 0,
                "readback_settings": {},
                "updates": 0,
                "configuration": None,
            }

            class FakeCli:
                def __init__(self, *args):
                    pass

                def run(self, args, **kwargs):
                    if args == ["apps", "get", "oc-fixture"]:
                        return app
                    if args == ["secrets", "list-scopes"]:
                        return {"scopes": external["scopes"]}
                    if args[:2] == ["secrets", "create-scope"]:
                        external["scopes"] = [{"name": args[2]}]
                        return {}
                    if args == ["secrets", "list-secrets", "fixture"]:
                        return {"secrets": external["metadata"]}
                    if args[:2] == ["secrets", "put-secret"]:
                        assert args[2:] == ["--json", args[-1]]
                        external["configuration"] = json.loads(
                            json.loads(Path(args[-1][1:]).read_text())["string_value"]
                        )
                        external["metadata"] = [
                            {"key": "runtime", "last_updated_timestamp": 1}
                        ]
                        return {}
                    if args[:2] == ["jobs", "list"]:
                        return {"jobs": []}
                    if args[:2] == ["workspace", "mkdirs"]:
                        return {}
                    if args[:2] == ["workspace", "import"]:
                        external["files"][args[2]] = Path(
                            args[args.index("--file") + 1]
                        ).read_bytes()
                        return {}
                    if args[:2] == ["workspace", "export"]:
                        return {
                            "content": base64.b64encode(
                                external["files"][args[2]]
                            ).decode()
                        }
                    if args[:2] == ["jobs", "create"]:
                        external["settings"] = json.loads(
                            Path(args[args.index("--json") + 1][1:]).read_text()
                        )
                        external["job_creations"] += 1
                        return {"job_id": 42}
                    if args == ["jobs", "get", "42"]:
                        observed = copy.deepcopy(external["settings"])
                        observed.update(
                            email_notifications={},
                            webhook_notifications={},
                            format="MULTI_TASK",
                        )
                        observed.update(external["readback_settings"])
                        for task in observed["tasks"]:
                            task.update(
                                disabled=False,
                                email_notifications={},
                                min_retry_interval_millis=0,
                                retry_on_timeout=False,
                                run_if="ALL_SUCCESS",
                                timeout_seconds=0,
                            )
                        return {"settings": observed}
                    if args[:2] == ["apps", "create-update"]:
                        assert args[2:] == ["oc-fixture", "--json", args[-1]]
                        app["resources"] = json.loads(
                            Path(args[args.index("--json") + 1][1:]).read_text()
                        )["app"]["resources"]
                        external["updates"] += 1
                        return app
                    raise AssertionError(args)

            args = SimpleNamespace(
                state_directory=directory,
                installation="fixture",
                profile="chosen",
                cli=Path("/unused"),
                existing_profile=profile,
            )
            with patch.object(deployment, "Cli", FakeCli):
                profile_before = profile.read_bytes()
                deployment.configure_existing(args)
                deployment.configure_existing(args)
                self.assertEqual(
                    external["configuration"]["OPENCONTRACTS_DATABASE_MODE"], "existing"
                )
                self.assertEqual(profile.read_bytes(), profile_before)
                configured = json.loads((directory / "installation.json").read_text())
                self.assertEqual(configured["phase"], "configured")
                self.assertFalse(configured["database_permissions_verified"])
                self.assertEqual(
                    configured["selection_sha256"],
                    hashlib.sha256(profile_before).hexdigest(),
                )
                self.assertEqual(external["updates"], 1)
                self.assertEqual(external["job_creations"], 1)
                self.assertEqual(configured["docling_job_id"], 42)
                self.assertEqual(
                    configured["docling_job_settings"], external["settings"]
                )
                self.assertEqual(len(external["files"]), 2)
                external["readback_settings"] = {
                    "schedule": {
                        "quartz_cron_expression": "0 0 * * * ?",
                        "timezone_id": "UTC",
                        "pause_status": "UNPAUSED",
                    }
                }
                with self.assertRaisesRegex(
                    ValueError, "Owned Docling job settings differ"
                ):
                    deployment.configure_existing(args)
                self.assertEqual(external["updates"], 1)
                self.assertEqual(external["job_creations"], 1)
                self.assertEqual(
                    json.loads((directory / "installation.json").read_text())[
                        "docling_job_settings"
                    ],
                    external["settings"],
                )
                external["readback_settings"] = {}
                for path, original in list(external["files"].items()):
                    with self.subTest(parser_file=Path(path).name):
                        external["files"][
                            path
                        ] = b"changed owned workspace parser code\n"
                        before = external["updates"]
                        with self.assertRaisesRegex(
                            ValueError, "source-bound Docling bytes differ"
                        ):
                            deployment.configure_existing(args)
                        self.assertEqual(external["updates"], before)
                        external["files"][path] = original


class AppCreationReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.now = 0
        self.snapshots = [
            {
                "compute_status": {"state": "STARTING"},
                "app_status": {"state": "UNAVAILABLE"},
                "service_principal_client_id": None,
                "resources": None,
            },
            {
                "compute_status": {"state": "STOPPED"},
                "service_principal_client_id": "new-principal",
            },
        ]
        branch = "projects/existing/branches/production"
        database = branch + "/databases/db"
        resources = [
            {
                "name": "postgres",
                "postgres": {
                    "branch": branch,
                    "database": database,
                    "permission": "CAN_CONNECT_AND_CREATE",
                },
            }
        ]
        source = {"name": "oc-source", "id": "source-app", "resources": resources}
        profile = self.root / "profile.json"
        profile.write_text(
            json.dumps(
                {
                    "format": "opencontracts-existing-installation.v1",
                    "source_app": source,
                    "lakebase": {
                        "branch": branch,
                        "database": database,
                        "schema": "opencontracts",
                    },
                    "git_repository": {
                        "url": "https://github.com/pi-squared/OpenContracts.git",
                        "provider": "gitHub",
                    },
                    "configuration_secret": {"scope": "fixture", "key": "runtime"},
                    "runtime_configuration": {
                        "OPENCONTRACTS_SCHEMA": "opencontracts",
                        "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/workflow-packages",
                        "WORKFLOW_INSTALL_HASHES": "[]",
                        "PILOT_USERNAME": "pilot-owner",
                    },
                }
            )
        )
        self.args = SimpleNamespace(
            state_directory=self.root / "state",
            cli=Path("/unused"),
            profile="chosen",
            installation="testing-fixture",
            existing_profile=profile,
        )
        self.calls = []
        self.created = None
        self.current = None
        self.reads = 0
        self.request_timeout = False
        fixture = self

        class FakeCli:
            def __init__(self, *args):
                pass

            def run(self, args, **kwargs):
                fixture.calls.append(args)
                if args == ["auth", "profiles"]:
                    return {
                        "profiles": [
                            {
                                "name": "chosen",
                                "host": "https://workspace.invalid",
                                "valid": True,
                            }
                        ]
                    }
                if args == ["apps", "get", "oc-source"]:
                    return source
                if args == ["postgres", "get-branch", branch]:
                    return {"name": branch, "status": {"state": "READY"}}
                if args == ["postgres", "get-database", database]:
                    return {
                        "name": database,
                        "status": {"postgres_database": "databricks_postgres"},
                    }
                if args == ["apps", "list"]:
                    return [source, fixture.current] if fixture.current else [source]
                if args[:2] == ["apps", "create"]:
                    body = json.loads(
                        Path(args[args.index("--json") + 1][1:]).read_text()
                    )
                    fixture.created = {
                        **body,
                        "id": "new-app",
                        "url": "https://new.invalid",
                        "compute_status": {"state": "STARTING"},
                    }
                    fixture.current = copy.deepcopy(fixture.created)
                    return copy.deepcopy(fixture.created)
                if args == ["apps", "get", "oc-testing-fixture"]:
                    if fixture.request_timeout:
                        assert 0 < kwargs["timeout"] <= 120
                        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
                    snapshot = fixture.snapshots[
                        min(fixture.reads, len(fixture.snapshots) - 1)
                    ]
                    fixture.reads += 1
                    fixture.current = {
                        **copy.deepcopy(fixture.created),
                        **copy.deepcopy(snapshot),
                    }
                    return copy.deepcopy(fixture.current)
                raise AssertionError(args)

        self.addCleanup(patch.stopall)
        patch.object(deployment, "Cli", FakeCli).start()
        patch("time.monotonic", lambda: self.now).start()

        def advance(seconds):
            self.now += seconds

        patch("time.sleep", advance).start()

    def journal(self):
        return json.loads((self.args.state_directory / "installation.json").read_text())

    def test_starting_app_waits_for_stopped_principal_and_resource_readiness(self):
        deployment.provision(self.args)
        state = self.journal()
        self.assertEqual(state["phase"], "provisioned")
        self.assertEqual(state["app_id"], "new-app")
        self.assertEqual(state["service_principal_client_id"], "new-principal")
        self.assertEqual(state["resources"], self.created["resources"])
        self.assertGreater(self.reads, 1)
        self.assertEqual(sum(call[:2] == ["apps", "create"] for call in self.calls), 1)
        self.assertFalse(
            any(
                call[:2]
                in (
                    ["apps", "start"],
                    ["apps", "deploy"],
                    ["postgres", "create-project"],
                )
                for call in self.calls
            )
        )

    def test_stopped_app_waits_for_missing_principal_and_resource_bindings(self):
        self.snapshots[0]["compute_status"] = {"state": "STOPPED"}
        deployment.provision(self.args)
        self.assertEqual(self.journal()["service_principal_client_id"], "new-principal")
        self.assertEqual(self.journal()["resources"], self.created["resources"])
        self.assertGreater(self.reads, 1)

    def test_pending_creation_times_out_and_resumes_the_same_owned_app(self):
        self.snapshots = [self.snapshots[0]]
        with self.assertRaisesRegex(ValueError, "readiness timed out"):
            deployment.provision(self.args)
        state = self.journal()
        self.assertEqual(state["phase"], "admitted")
        self.assertEqual(state["app_creation_id"], "new-app")
        self.assertNotIn("app_id", state)
        self.snapshots = [
            {
                "compute_status": {"state": "STOPPED"},
                "service_principal_client_id": "new-principal",
            }
        ]
        deployment.provision(self.args)
        self.assertEqual(self.journal()["app_id"], "new-app")
        self.assertEqual(sum(call[:2] == ["apps", "create"] for call in self.calls), 1)

    def test_compute_error_and_active_state_are_rejected(self):
        for state in ("ERROR", "ACTIVE"):
            with self.subTest(compute_state=state):
                self.snapshots = [{"compute_status": {"state": state}}]
                with self.assertRaisesRegex(ValueError, "unexpected compute state"):
                    deployment.provision(self.args)
                self.assertNotIn("app_id", self.journal())
                self.assertEqual(
                    sum(call[:2] == ["apps", "create"] for call in self.calls), 1
                )

    def test_app_identity_movement_during_creation_is_rejected(self):
        self.snapshots[1]["id"] = "another-app"
        with self.assertRaisesRegex(ValueError, "identity changed during creation"):
            deployment.provision(self.args)
        self.assertEqual(self.journal()["app_creation_id"], "new-app")
        self.assertNotIn("app_id", self.journal())

    def test_git_identity_change_during_creation_is_rejected(self):
        self.snapshots[1]["git_repository"] = {
            "url": "https://unexpected.invalid/repo.git",
            "provider": "gitHub",
        }
        with self.assertRaisesRegex(
            ValueError, "Git repository changed during creation"
        ):
            deployment.provision(self.args)
        self.assertNotIn("app_id", self.journal())

    def test_resource_identity_change_during_creation_is_rejected(self):
        self.snapshots[1]["resources"] = [
            {
                "name": "unexpected",
                "secret": {"scope": "other", "key": "other", "permission": "READ"},
            }
        ]
        with self.assertRaisesRegex(
            ValueError, "resource bindings changed during creation"
        ):
            deployment.provision(self.args)
        self.assertNotIn("app_id", self.journal())

    def test_ownership_marker_movement_is_rejected(self):
        self.snapshots[1]["description"] = "unexpected-owner"
        with self.assertRaisesRegex(
            ValueError, "ownership marker changed during creation"
        ):
            deployment.provision(self.args)
        self.assertNotIn("app_id", self.journal())

    def test_unknown_app_name_collision_is_not_adopted(self):
        self.current = {
            "name": "oc-testing-fixture",
            "id": "unknown-app",
            "description": "unowned",
        }
        with self.assertRaisesRegex(ValueError, "Unknown App name collision"):
            deployment.provision(self.args)
        self.assertFalse(any(call[:2] == ["apps", "create"] for call in self.calls))
        self.assertFalse((self.args.state_directory / "installation.json").exists())

    def test_principal_identity_movement_before_stopped_is_rejected(self):
        self.snapshots[0]["service_principal_client_id"] = "first-principal"
        self.snapshots[1]["service_principal_client_id"] = "different-principal"
        with self.assertRaisesRegex(ValueError, "identity changed during creation"):
            deployment.provision(self.args)
        self.assertEqual(self.journal()["app_creation_principal"], "first-principal")
        self.assertNotIn("app_id", self.journal())

    def test_request_timeout_retains_owned_pending_creation(self):
        self.request_timeout = True
        with self.assertRaisesRegex(ValueError, "readiness timed out"):
            deployment.provision(self.args)
        self.assertEqual(self.journal()["app_creation_id"], "new-app")
        self.assertEqual(self.journal()["phase"], "admitted")
        self.assertNotIn("app_id", self.journal())


if __name__ == "__main__":
    unittest.main()
