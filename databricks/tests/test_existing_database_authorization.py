"""Explicit retained-database privileges through the controller and SQL adapters."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psycopg2

from tools import deploy_installation as controller


class ExistingAuthorizationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.statements = []
        self.member = False
        self.rights = {"schema": False, "tables": False, "sequences": False}
        self.deny_sequence = False
        self.sequence_warning = False
        self.drift = False
        self.retained_state_drift = None
        self.relation_reads = self.migration_reads = 0
        self.committed = False
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
        repo = {
            "url": "https://github.com/pi-squared/OpenContracts.git",
            "provider": "gitHub",
        }
        config = {
            "format": "opencontracts-existing-installation.v1",
            "source_app": {
                "name": "source",
                "id": "source-app",
                "service_principal_client_id": "source-principal",
                "resources": resources,
            },
            "lakebase": {
                "branch": branch,
                "database": database,
                "endpoint": branch + "/endpoints/primary",
                "schema": "retained",
                "schema_owner_role": "source-principal",
            },
            "git_repository": repo,
            "configuration_secret": {"scope": "fixture", "key": "runtime"},
            "runtime_configuration": {
                "OPENCONTRACTS_SCHEMA": "retained",
                "PILOT_USERNAME": "pilot",
                "WORKFLOW_PACKAGE_ROOT": "/Volumes/c/s/v/packages",
                "WORKFLOW_INSTALL_HASHES": "[]",
            },
        }
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps(config))
        self.profile_before = self.profile.read_bytes()
        self.state = {
            "installation": "fixture",
            "profile": "chosen",
            "host": "https://workspace.invalid",
            "app_name": "oc-fixture",
            "app_id": "new-app",
            "app_url": "https://new.invalid",
            "marker": "owned",
            "resources": resources,
            "git_repository": repo,
            "service_principal_client_id": "new-principal",
            "schema": "retained",
            "branch": branch,
            "database": database,
            "phase": "provisioned",
            "database_mode": "existing",
            "selection_sha256": hashlib.sha256(self.profile_before).hexdigest(),
        }
        controller.private_json(self.root / "installation.json", self.state)
        self.args = SimpleNamespace(
            state_directory=self.root,
            installation="fixture",
            profile="chosen",
            cli=Path("/unused"),
            existing_profile=self.profile,
        )
        app = {
            "id": "new-app",
            "url": "https://new.invalid",
            "description": "owned",
            "resources": resources,
            "git_repository": repo,
        }
        fixture = self

        class Cli:
            def __init__(self, *args):
                pass

            def run(self, args, **kwargs):
                if args == ["apps", "get", "oc-fixture"]:
                    return app
                raise AssertionError(args)

        client = SimpleNamespace(
            config=SimpleNamespace(host="https://workspace.invalid"),
            postgres=SimpleNamespace(
                get_endpoint=lambda **kw: SimpleNamespace(
                    name=branch + "/endpoints/primary",
                    status=SimpleNamespace(
                        hosts=SimpleNamespace(host="fixture.invalid")
                    ),
                ),
                get_database=lambda **kw: SimpleNamespace(
                    status=SimpleNamespace(postgres_database="fixture")
                ),
                generate_database_credential=lambda **kw: SimpleNamespace(
                    token="fixture"
                ),
            ),
            current_user=SimpleNamespace(
                me=lambda: SimpleNamespace(user_name="approved-operator")
            ),
        )

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, query, params=None):
                text = str(query)
                fixture.statements.append(text)
                self.rows = []
                self.row = None
                if "has_table_privilege" in text:
                    if "current_user" in text:
                        self.rows = []  # The operator already has access.
                        return
                    assert params == ("retained", *["new-principal"] * 4)
                elif "has_sequence_privilege" in text:
                    if "current_user" in text:
                        self.rows = []
                        return
                    assert params == ("retained", *["new-principal"] * 3)
                elif "has_schema_privilege" in text:
                    if "current_user" in text:
                        self.row = (True,)
                        return
                    assert params == ("new-principal", "retained")
                if "GRANT" in text:
                    if "SEQUENCES" in text:
                        if fixture.deny_sequence:
                            raise psycopg2.errors.InsufficientPrivilege(
                                "fixture sequence owner prerequisite"
                            )
                        if not fixture.sequence_warning:
                            fixture.rights["sequences"] = True
                    elif "TABLES" in text:
                        fixture.rights["tables"] = True
                    elif "SCHEMA" in text:
                        fixture.rights["schema"] = True
                    else:
                        fixture.member = True
                elif "pg_get_userbyid(nspowner)" in text:
                    self.row = ("source-principal",)
                elif "SELECT DISTINCT pg_get_userbyid" in text:
                    self.rows = [("source-principal",)]
                elif "pg_class" in text and "has_table_privilege" in text:
                    self.rows = (
                        []
                        if fixture.rights["tables"] and not fixture.drift
                        else [("data_table",)]
                    )
                elif "pg_class" in text and "has_sequence_privilege" in text:
                    self.rows = [] if fixture.rights["sequences"] else [("data_seq",)]
                elif "pg_class" in text:
                    fixture.relation_reads += 1
                    self.rows = [
                        ("data_table", "r", "source-principal"),
                        ("django_migrations", "r", "source-principal"),
                        ("data_seq", "S", "source-principal"),
                    ]
                    if (
                        fixture.retained_state_drift == "ownership"
                        and fixture.relation_reads > 1
                    ):
                        self.rows[0] = ("data_table", "r", "unexpected-owner")
                elif "has_schema_privilege" in text:
                    self.row = (fixture.rights["schema"],)
                elif "pg_roles" in text:
                    self.row = (True,)
                elif "pg_has_role" in text:
                    self.row = (fixture.member,)
                elif "to_regclass" in text:
                    self.row = ("retained.django_migrations",)
                elif "django_migrations" in text:
                    fixture.migration_reads += 1
                    self.rows = [("fixture", "0001")]
                    if (
                        fixture.retained_state_drift == "migration"
                        and fixture.migration_reads > 1
                    ):
                        self.rows.append(("fixture", "0002"))

            def fetchone(self):
                return self.row

            def fetchall(self):
                return self.rows

        class Connection:
            def __enter__(self):
                self.before = fixture.rights.copy()
                return self

            def __exit__(self, kind, *args):
                fixture.committed = kind is None
                if kind:
                    fixture.rights = self.before
                return False

            def cursor(self):
                return Cursor()

        self.addCleanup(patch.stopall)
        patch.object(controller, "Cli", Cli).start()
        patch("databricks.sdk.WorkspaceClient", return_value=client).start()
        patch("psycopg2.connect", return_value=Connection()).start()

    def test_direct_access_preserves_owners_and_never_grants_owner_membership(self):
        controller.authorize_existing(self.args)
        state = json.loads((self.root / "installation.json").read_text())
        self.assertEqual(state["database_permission_mode"], "existing-direct")
        self.assertTrue(state["database_permissions_verified"])
        self.assertFalse(state["owner_role_membership_claimed"])
        self.assertFalse(state["ownership_transferred"])
        self.assertFalse(self.member)
        self.assertTrue(all(self.rights.values()))
        self.assertEqual(self.profile.read_bytes(), self.profile_before)

    def test_sequence_owner_prerequisite_rolls_back_and_never_claims_verification(self):
        self.deny_sequence = True
        old = json.loads((self.root / "installation.json").read_text())
        old["database_permissions_verified"] = True
        controller.private_json(self.root / "installation.json", old)
        with self.assertRaisesRegex(
            ValueError, "Retained owner must grant USAGE and SELECT"
        ):
            controller.authorize_existing(self.args)
        self.assertFalse(self.committed)
        self.assertFalse(any(self.rights.values()))
        self.assertFalse(self.member)
        state = json.loads((self.root / "installation.json").read_text())
        self.assertFalse(state["database_permissions_verified"])
        self.assertFalse(state["owner_role_membership_claimed"])

    def test_actual_permission_drift_fails_even_after_grants(self):
        self.drift = True
        with self.assertRaisesRegex(ValueError, "CRUD permissions are unavailable"):
            controller.authorize_existing(self.args)
        self.assertFalse(self.committed)
        self.assertFalse(
            json.loads((self.root / "installation.json").read_text())[
                "database_permissions_verified"
            ]
        )

    def test_sequence_grant_warning_requires_actual_privileges_and_owner_action(self):
        self.sequence_warning = True
        with self.assertRaisesRegex(
            ValueError, "Retained owner must grant USAGE and SELECT"
        ):
            controller.authorize_existing(self.args)
        self.assertFalse(self.committed)
        self.assertFalse(any(self.rights.values()))

    def test_configured_installation_cannot_publish_with_unverified_database_access(
        self,
    ):
        state = json.loads((self.root / "installation.json").read_text())
        state.update(phase="configured", database_permissions_verified=False)
        controller.private_json(self.root / "installation.json", state)
        with self.assertRaisesRegex(
            ValueError, "verified existing database permissions"
        ):
            controller.publish_git(self.args)
        self.assertFalse(self.statements)

    def test_retained_ownership_and_migration_changes_abort_authorization(self):
        for drift in ("ownership", "migration"):
            self.retained_state_drift = drift
            self.relation_reads = self.migration_reads = 0
            with self.subTest(drift=drift), self.assertRaisesRegex(
                ValueError, "changed during authorization"
            ):
                controller.authorize_existing(self.args)
            self.assertFalse(self.committed)
            self.assertFalse(any(self.rights.values()))
