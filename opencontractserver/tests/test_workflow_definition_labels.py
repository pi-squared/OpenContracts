"""Native definition verification must be independent of database label ordering."""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db.models import Case, IntegerField, Value, When
from django.db.models.query import QuerySet
from django.test import TestCase

from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.extracts.definition_installer import install_definitions
from opencontractserver.extracts.workflows import package, resolve_response_model


class WorkflowDefinitionLabelTests(TestCase):
    def test_verify_only_accepts_unchanged_labels_in_different_database_order(self):
        user = get_user_model().objects.create_user(username="label-order-regression")
        schema = (
            b"from pydantic import BaseModel\nclass Result(BaseModel):\n"
            b"    value: str\ndef response_model(key):\n    return Result\n"
        )
        labels = [
            {
                "text": name,
                "label_type": "TOKEN_LABEL",
                "color": "#112233",
                "description": "Fixture",
                "icon": "tag",
            }
            for name in ["alpha", "Beta"]
        ]
        manifest = {
            "format": "opencontracts-workflow.v1",
            "identity": "Label order regression",
            "version": "1",
            "owner": "local-fixture",
            "compatibility": {"pydantic_major": 2},
            "response_factory": {"file": "schema.py", "function": "response_model"},
            "files": {"schema.py": hashlib.sha256(schema).hexdigest()},
            "labels": labels,
            "columns": [
                {
                    "key": "fixture",
                    "name": "Fixture",
                    "query": "Fixture",
                    "instructions": "Fixture",
                    "display_order": 0,
                }
            ],
        }
        content = json.dumps(manifest).encode()
        identity = hashlib.sha256(content).hexdigest()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"WORKFLOW_PACKAGE_ROOT": temporary}
        ):
            directory = Path(temporary) / identity
            directory.mkdir()
            (directory / "manifest.json").write_bytes(content)
            (directory / "schema.py").write_bytes(schema)
            installed = install_definitions(identity, user.username)
            # Native definitions are sets. Reproduce a different SQL ordering
            # while keeping real ORM rows and all actual permission checks.
            original = QuerySet.order_by

            def different_order(queryset, *fields):
                if queryset.model is AnnotationLabel and fields == ("text",):
                    return original(
                        queryset,
                        Case(
                            When(text="alpha", then=Value(0)),
                            default=Value(1),
                            output_field=IntegerField(),
                        ),
                    )
                return original(queryset, *fields)

            with patch.object(QuerySet, "order_by", different_order):
                self.assertEqual(
                    install_definitions(identity, user.username, verify_only=True),
                    installed,
                )
            AnnotationLabel.objects.filter(creator=user, text="alpha").update(
                color="#998877"
            )
            with self.assertRaisesRegex(ValueError, "labels have changed"):
                install_definitions(identity, user.username, verify_only=True)
            from tools.local_workspace.bootstrap import install_workspace_workflows

            report = install_workspace_workflows(user.username)
            self.assertEqual(report[0]["status"], "edited")
            self.assertEqual(
                AnnotationLabel.objects.get(creator=user, text="alpha").color, "#998877"
            )
            # Availability must not silently re-certify edits, and corrupt
            # package bytes must still fail rather than being treated as drift.
            with self.assertRaisesRegex(ValueError, "labels have changed"):
                install_definitions(identity, user.username, verify_only=True)
            (directory / "schema.py").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                install_workspace_workflows(user.username)
        package.cache_clear()
        resolve_response_model.cache_clear()
