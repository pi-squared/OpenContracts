"""Exercise the public typed workflow boundary with a domain-neutral fixture."""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

from pydantic import ValidationError  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "port/python"))
from databricks_port.workflows import package, resolve_response_model  # noqa: E402

FIXTURE = b"""from pydantic import BaseModel, ConfigDict, field_validator
class Evidence(BaseModel):
    page: int
    quote: str
class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence: list[Evidence]
    count: int
    @field_validator("count")
    @classmethod
    def nonnegative(cls, value):
        if value < 0:
            raise ValueError("negative count")
        return value
def response_model(key):
    return Answer
"""


class WorkflowPackageTests(unittest.TestCase):
    def setUp(self):
        package.cache_clear()
        resolve_response_model.cache_clear()
        self.storage = tempfile.TemporaryDirectory()
        self.addCleanup(self.storage.cleanup)
        manifest = {
            "format": "opencontracts-workflow.v1",
            "identity": "conformance",
            "version": "1",
            "owner": "test-fixture",
            "compatibility": {"pydantic_major": 2},
            "columns": [{"key": "count"}],
            "response_factory": {"file": "schema.py", "function": "response_model"},
            "files": {"schema.py": hashlib.sha256(FIXTURE).hexdigest()},
        }
        content = json.dumps(manifest).encode()
        self.sha = hashlib.sha256(content).hexdigest()
        self.directory = Path(self.storage.name) / self.sha
        self.directory.mkdir()
        (self.directory / "manifest.json").write_bytes(content)
        (self.directory / "schema.py").write_bytes(FIXTURE)
        self.environment = patch.dict(
            os.environ, {"WORKFLOW_PACKAGE_ROOT": self.storage.name}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.token = "workflow:" + self.sha + ":count"

    def test_nested_response_and_owner_validator_survive_install(self):
        model = resolve_response_model(self.token)
        answer = model.model_validate(
            {"count": 2, "evidence": [{"page": 1, "quote": "fixture"}]}
        )
        self.assertEqual(answer.evidence[0].page, 1)
        with self.assertRaises(ValidationError):
            model.model_validate({"count": -1, "evidence": []})

    def test_missing_column_and_changed_source_fail_before_execution(self):
        with self.assertRaises(ValueError):
            resolve_response_model("workflow:" + self.sha + ":missing")
        package.cache_clear()
        (self.directory / "schema.py").write_bytes(
            b'raise RuntimeError("must not execute")'
        )
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            resolve_response_model(self.token)

    def test_manifest_hash_and_invalid_pointer_are_rejected(self):
        (self.directory / "manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            resolve_response_model(self.token)
        with self.assertRaises(ValueError):
            resolve_response_model("workflow:../../outside:count")

    def test_owner_label_policy_is_hash_verified_and_domain_neutral(self):
        from databricks_port.workflows import resolve_label_policy

        policy = {
            "format": "opencontracts-label-policy.v1",
            "version": "1",
            "owner_approval": {"approved_on": "2026-10-05", "source": "fixture"},
            "evidence": {
                "state_field": "state",
                "eligible_states": ["supported"],
                "by_column": {"count": ["count_evidence"]},
                "applicability_gate": False,
            },
            "source_rules": [],
            "finding_document_rules": [],
            "source_identity_rules": [],
        }
        content = json.dumps(policy).encode()
        manifest = json.loads((self.directory / "manifest.json").read_text())
        manifest["labels"] = [
            {
                "key": "count_evidence",
                "text": "Fixture count evidence",
                "label_type": "TOKEN_LABEL",
            }
        ]
        manifest["label_policy"] = {
            "file": "label-policy.json",
            "format": policy["format"],
        }
        manifest["files"]["label-policy.json"] = hashlib.sha256(content).hexdigest()
        raw = json.dumps(manifest).encode()
        identity = hashlib.sha256(raw).hexdigest()
        destination = Path(self.storage.name) / identity
        destination.mkdir()
        (destination / "manifest.json").write_bytes(raw)
        (destination / "schema.py").write_bytes(FIXTURE)
        (destination / "label-policy.json").write_bytes(content)
        verified_manifest, verified_policy = resolve_label_policy(identity)
        self.assertEqual(verified_manifest["owner"], "test-fixture")
        self.assertEqual(
            verified_policy["evidence"]["by_column"], {"count": ["count_evidence"]}
        )
        package.cache_clear()
        resolve_label_policy.cache_clear()
        (destination / "label-policy.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            resolve_label_policy(identity)


if __name__ == "__main__":
    unittest.main()
