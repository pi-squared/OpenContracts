"""Bootstrap observes retained state through the PostgreSQL boundary."""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# Test the runtime package assembled from declared overlays, including sources
# maintained outside port/python. Keep it alive for this test process.
RUNTIME_SOURCE = tempfile.TemporaryDirectory()
for overlay in json.loads((ROOT / "upstream.lock.json").read_text())["overlays"]:
    if overlay["target"].startswith("databricks_port/"):
        target = Path(RUNTIME_SOURCE.name) / overlay["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / overlay["source"], target)
sys.path.insert(0, RUNTIME_SOURCE.name)
from databricks_port import lakebase  # noqa: E402


class BootstrapFixture:
    def setUp(self):
        self.statements = []
        self.missing = None
        self.secret = "retained-signing-key"
        self.revoked_database_permission = None
        fixture = self

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, statement, params=None):
                text = str(statement)
                fixture.statements.append(text)
                self.rows = []
                if (
                    "has_schema_privilege" in text
                    or "has_table_privilege" in text
                    or "has_sequence_privilege" in text
                ):
                    assert "current_user" in text
                    assert params == ("retained",)
                if "has_schema_privilege" in text:
                    self.row = (fixture.revoked_database_permission != "schema",)
                elif "has_table_privilege" in text:
                    self.rows = (
                        [("retained_table",)]
                        if fixture.revoked_database_permission == "table"
                        else []
                    )
                elif "has_sequence_privilege" in text:
                    self.rows = (
                        [("retained_sequence",)]
                        if fixture.revoked_database_permission == "sequence"
                        else []
                    )
                elif "pg_namespace" in text:
                    self.row = None if fixture.missing == "schema" else (1,)
                elif "to_regclass" in text:
                    self.row = (
                        (None,) if fixture.missing == "table" else ("retained-table",)
                    )
                elif "django_secret" in text:
                    self.row = (fixture.secret,) if fixture.secret else None
                else:
                    self.row = None

            def fetchone(self):
                return self.row

            def fetchall(self):
                return self.rows

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def cursor(self):
                return Cursor()

            def close(self):
                pass

        self.addCleanup(patch.stopall)
        patch.dict(
            os.environ,
            {
                "OPENCONTRACTS_DATABASE_MODE": "existing",
                "OPENCONTRACTS_SCHEMA": "retained",
                "PGHOST": "fixture.invalid",
                "PGDATABASE": "fixture",
                "PGUSER": "fixture",
                "LAKEBASE_ENDPOINT": "fixture",
            },
        ).start()
        client = SimpleNamespace(
            config=SimpleNamespace(client_id="fixture"),
            postgres=SimpleNamespace(
                generate_database_credential=lambda **kwargs: SimpleNamespace(
                    token="fixture",
                    expire_time=SimpleNamespace(seconds=time.time() + 3600),
                )
            ),
        )
        patch.object(lakebase, "WorkspaceClient", return_value=client).start()
        patch("psycopg2.connect", return_value=Connection()).start()


class ExistingBootstrapTests(BootstrapFixture, unittest.TestCase):
    def test_existing_bootstrap_reads_signing_key_without_creation_or_insertion(self):
        lakebase.bootstrap()
        self.assertEqual(os.environ["DJANGO_SECRET_KEY"], "retained-signing-key")
        self.assertTrue(any("READ ONLY" in text for text in self.statements))
        self.assertFalse(
            any(
                word in text
                for text in self.statements
                for word in ("CREATE ", "INSERT ", "UPDATE ", "GRANT ")
            )
        )

    def test_existing_bootstrap_rejects_revoked_database_permissions_without_regranting(
        self,
    ):
        for permission in ("schema", "table", "sequence"):
            self.revoked_database_permission = permission
            with self.subTest(permission=permission), self.assertRaisesRegex(
                ValueError, "permissions are unavailable"
            ):
                lakebase.bootstrap()
        self.assertFalse(any("GRANT " in text for text in self.statements))


class ExistingStartupTests(BootstrapFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.actions = []
        self.pending = False
        self.user = SimpleNamespace(is_active=True, id=7, pk=7)
        fixture = self
        django = ModuleType("django")
        django.setup = lambda: fixture.actions.append("setup")
        conf = ModuleType("django.conf")
        conf.settings = SimpleNamespace(PILOT_USERNAME="pilot")
        db = ModuleType("django.db")

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, statement, params=None):
                text = str(statement)
                fixture.statements.append(text)
                self.row = (
                    (json.dumps({"fieldset_id": 101, "labelset_id": 202}),)
                    if getattr(fixture, "registered", True)
                    and "workflow-definitions" in str(params)
                    else None
                )

            def fetchone(self):
                return self.row

        db.connection = SimpleNamespace(cursor=lambda: Cursor())
        from contextlib import nullcontext

        db.transaction = SimpleNamespace(atomic=nullcontext)
        auth = ModuleType("django.contrib.auth")

        class User:
            class DoesNotExist(Exception):
                pass

            class Manager:
                def get(self, **kwargs):
                    fixture.actions.append("user.get")
                    if fixture.user is None:
                        raise User.DoesNotExist()
                    return fixture.user

                def get_or_create(self, **kwargs):
                    fixture.actions.append("user.get_or_create")
                    if fixture.user is None:
                        fixture.user = SimpleNamespace(
                            is_active=True,
                            pk=7,
                            id=7,
                            save=lambda: fixture.actions.append("user.save"),
                            set_unusable_password=lambda: fixture.actions.append(
                                "password"
                            ),
                        )
                        return fixture.user, True
                    return fixture.user, False

            objects = Manager()

        auth.get_user_model = lambda: User
        management = ModuleType("django.core.management")
        management.call_command = lambda name, **kwargs: fixture.actions.append(name)
        migrations = ModuleType("django.db.migrations.executor")

        class Executor:
            def __init__(self, connection):
                self.loader = SimpleNamespace(
                    check_consistent_history=lambda connection: fixture.actions.append(
                        "check-history"
                    ),
                    graph=SimpleNamespace(leaf_nodes=lambda: [("fixture", "leaf")]),
                )

            def migration_plan(self, nodes):
                return [("fixture", "pending")] if fixture.pending else []

        migrations.MigrationExecutor = Executor
        patch.dict(
            sys.modules,
            {
                "django": django,
                "django.conf": conf,
                "django.db": db,
                "django.contrib.auth": auth,
                "django.core.management": management,
                "django.db.migrations.executor": migrations,
            },
        ).start()
        patch.dict(
            os.environ, {"WORKFLOW_INSTALL_HASHES": "[]", "PILOT_USERNAME": "pilot"}
        ).start()

    def initialize(self):
        from databricks_port.startup import initialize

        return initialize()

    def test_existing_startup_checks_migrations_and_user_without_writes(self):
        self.initialize()
        self.assertIn("check-history", self.actions)
        self.assertIn("user.get", self.actions)
        self.assertNotIn("migrate", self.actions)
        self.assertNotIn("user.get_or_create", self.actions)
        self.assertFalse(
            any(
                word in text
                for text in self.statements
                for word in ("CREATE ", "INSERT ", "UPDATE ", "GRANT ")
            )
        )

    def configure_package(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.package_root = Path(temporary.name)
        content = (
            b"from pydantic import BaseModel\ndef response_model(field):\n"
            b" class Response(BaseModel):\n  result: str\n return Response\n"
        )
        manifest = {
            "format": "opencontracts-workflow.v1",
            "compatibility": {"pydantic_major": 2},
            "identity": "fixture",
            "version": "1",
            "owner": "fixture-owner",
            "response_factory": {"file": "schema.py", "function": "response_model"},
            "files": {"schema.py": hashlib.sha256(content).hexdigest()},
            "columns": [
                {
                    "key": "field",
                    "name": "Finding",
                    "query": "retain",
                    "instructions": "fixture",
                    "display_order": 1,
                }
            ],
            "labels": [
                {
                    "text": "Evidence",
                    "label_type": "TOKEN_LABEL",
                    "color": "#000000",
                    "description": "fixture",
                    "icon": "tag",
                }
            ],
        }
        raw = json.dumps(manifest).encode()
        identity = hashlib.sha256(raw).hexdigest()
        directory = self.package_root / identity
        directory.mkdir()
        (directory / "manifest.json").write_bytes(raw)
        (directory / "schema.py").write_bytes(content)
        from databricks_port.workflows import package, resolve_response_model

        package.cache_clear()
        resolve_response_model.cache_clear()
        patch.dict(
            os.environ,
            {
                "WORKFLOW_PACKAGE_ROOT": str(self.package_root),
                "WORKFLOW_INSTALL_HASHES": json.dumps([identity]),
            },
        ).start()
        self.registered = True
        self.permission_ok = True
        self.column_changed = False
        fixture = self

        class Records:
            def __init__(self, kind):
                self.kind = kind

            def order_by(self, *args):
                return self

            def values(self, *fields):
                if self.kind == "columns":
                    return [
                        {
                            "name": "Finding",
                            "query": "changed" if fixture.column_changed else "retain",
                            "instructions": "fixture",
                            "display_order": 1,
                            "output_type": "workflow:" + identity + ":field",
                            **{
                                x: None
                                for x in (
                                    "task_name",
                                    "extract_is_list",
                                    "must_contain_text",
                                    "match_text",
                                    "limit_to_label",
                                    "is_manual_entry",
                                )
                            },
                        }
                    ]
                return [{x: manifest["labels"][0][x] for x in fields}]

            def count(self):
                return 1

            def all(self):
                return [
                    SimpleNamespace(
                        _meta=SimpleNamespace(
                            model_name=(
                                "column"
                                if self.kind == "columns"
                                else "annotationlabel"
                            )
                        ),
                        creator_id=7,
                    )
                ]

        name = "fixture 1 · " + identity[:12]
        description = "Workflow package SHA-256: " + identity + "\nOwner: fixture-owner"
        fieldset = SimpleNamespace(
            pk=101,
            name=name,
            description=description,
            creator_id=7,
            columns=Records("columns"),
            _meta=SimpleNamespace(model_name="fieldset"),
        )
        labelset = SimpleNamespace(
            pk=202,
            title=name,
            description=description,
            creator_id=7,
            annotation_labels=Records("labels"),
            _meta=SimpleNamespace(model_name="labelset"),
        )

        class Manager:
            def __init__(self, obj):
                self.obj = obj

            def get(self, **kwargs):
                return self.obj

            def get_or_create(self, **kwargs):
                fixture.actions.append("definition.get_or_create")
                return self.obj, False

        extracts = ModuleType("opencontractserver.extracts.models")
        extracts.Fieldset = SimpleNamespace(objects=Manager(fieldset))
        extracts.Column = SimpleNamespace(
            _meta=SimpleNamespace(
                get_field=lambda name: SimpleNamespace(get_default=lambda: None)
            )
        )
        annotations = ModuleType("opencontractserver.annotations.models")
        annotations.LabelSet = SimpleNamespace(objects=Manager(labelset))
        annotations.AnnotationLabel = SimpleNamespace()
        enums = ModuleType("opencontractserver.types.enums")
        enums.PermissionTypes = SimpleNamespace(CRUD="CRUD")
        permissioning = ModuleType("opencontractserver.utils.permissioning")
        permissioning.set_permissions_for_obj_to_user = (
            lambda *args, **kwargs: fixture.actions.append("permission.write")
        )
        permissioning.get_users_permissions_for_obj = lambda user, obj: (
            {
                action + "_" + obj._meta.model_name
                for action in ("create", "read", "update", "remove")
            }
            if fixture.permission_ok
            else set()
        )
        patch.dict(
            sys.modules,
            {
                "opencontractserver.extracts.models": extracts,
                "opencontractserver.annotations.models": annotations,
                "opencontractserver.types.enums": enums,
                "opencontractserver.utils.permissioning": permissioning,
            },
        ).start()

    def test_existing_registered_packages_are_verified_without_install_or_permission_writes(
        self,
    ):
        self.configure_package()
        result = self.initialize()
        self.assertEqual(result[0]["fieldset_id"], 101)
        self.assertEqual(result[0]["labelset_id"], 202)
        self.assertNotIn("definition.get_or_create", self.actions)
        self.assertNotIn("permission.write", self.actions)
        self.assertFalse(any("INSERT " in text for text in self.statements))

    def test_missing_schema_or_port_table_fails_without_creation(self):
        for missing in ("schema", "table"):
            self.missing = missing
            with self.subTest(missing=missing), self.assertRaisesRegex(
                ValueError, "is missing"
            ):
                self.initialize()
        self.assertFalse(
            any("CREATE " in text or "INSERT " in text for text in self.statements)
        )

    def test_missing_signing_key_fails_without_replacing_it(self):
        self.secret = None
        with self.assertRaisesRegex(ValueError, "signing key is missing"):
            self.initialize()
        self.assertFalse(any("INSERT " in text for text in self.statements))

    def test_pending_migrations_are_rejected_without_migrate(self):
        self.pending = True
        with self.assertRaisesRegex(ValueError, "pending migrations"):
            self.initialize()
        self.assertNotIn("migrate", self.actions)

    def test_missing_pilot_is_rejected_without_user_creation(self):
        self.user = None
        with self.assertRaisesRegex(ValueError, "pilot user is missing"):
            self.initialize()
        self.assertNotIn("user.get_or_create", self.actions)

    def test_inactive_pilot_is_rejected_without_enabling_it(self):
        self.user.is_active = False
        with self.assertRaisesRegex(ValueError, "pilot user is inactive"):
            self.initialize()
        self.assertFalse(self.user.is_active)
        self.assertNotIn("user.save", self.actions)

    def test_changed_package_bytes_are_rejected_without_definition_writes(self):
        self.configure_package()
        directory = next(self.package_root.iterdir())
        (directory / "schema.py").write_text("changed package source\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.initialize()
        self.assertNotIn("definition.get_or_create", self.actions)
        self.assertNotIn("permission.write", self.actions)

    def test_unregistered_package_is_rejected_without_installation(self):
        self.configure_package()
        self.registered = False
        with self.assertRaisesRegex(ValueError, "not registered"):
            self.initialize()
        self.assertNotIn("definition.get_or_create", self.actions)
        self.assertNotIn("permission.write", self.actions)

    def test_native_definition_drift_is_rejected_without_overwriting(self):
        self.configure_package()
        self.column_changed = True
        with self.assertRaisesRegex(ValueError, "definitions have changed"):
            self.initialize()
        self.assertNotIn("permission.write", self.actions)

    def test_native_permission_drift_is_rejected_without_regranting(self):
        self.configure_package()
        self.permission_ok = False
        with self.assertRaisesRegex(ValueError, "permissions have changed"):
            self.initialize()
        self.assertNotIn("permission.write", self.actions)

    def test_owned_default_preserves_migration_user_creation_and_definition_installation(
        self,
    ):
        self.configure_package()
        self.user = None
        os.environ.pop("OPENCONTRACTS_DATABASE_MODE", None)
        self.initialize()
        self.assertIn("migrate", self.actions)
        self.assertIn("user.get_or_create", self.actions)
        self.assertIn("user.save", self.actions)
        self.assertIn("permission.write", self.actions)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
        self.assertFalse(self.user.is_usage_capped)
        self.assertTrue(any("CREATE " in text for text in self.statements))
        self.assertTrue(any("INSERT " in text for text in self.statements))
