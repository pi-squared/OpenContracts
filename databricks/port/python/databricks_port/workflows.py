"""Resolve typed models from hash-verified, maintainer-installed workflow packages."""

import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

TOKEN = re.compile(r"workflow:([0-9a-f]{64}):([a-z][a-z0-9_]{0,127})")


def verified(content, expected):
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Installed workflow package hash mismatch")
    return content


@lru_cache(maxsize=32)
def package(package_hash):
    if not re.fullmatch(r"[0-9a-f]{64}", package_hash):
        raise ValueError("Installed workflow identity must be a SHA-256 hash")
    root = os.environ["WORKFLOW_PACKAGE_ROOT"].rstrip("/")
    if root.startswith("/Volumes/"):
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()

        def read(name):
            download = client.files.download(root + "/" + package_hash + "/" + name)
            try:
                return download.contents.read()
            finally:
                download.contents.close()

    else:
        directory = Path(root).resolve() / package_hash

        def read(name):
            path = (directory / name).resolve()
            if not path.is_relative_to(directory):
                raise ValueError("Workflow file escapes installed package")
            return path.read_bytes()

    manifest = json.loads(verified(read("manifest.json"), package_hash))
    if manifest["format"] != "opencontracts-workflow.v1":
        raise ValueError("Unsupported workflow package format")
    if manifest.get("compatibility", {}).get("pydantic_major") != 2:
        raise ValueError("Workflow must declare Pydantic 2 compatibility")
    if (
        not manifest.get("identity")
        or not manifest.get("version")
        or not manifest.get("owner")
    ):
        raise ValueError("Workflow identity, version and owner are required")
    factory = manifest["response_factory"]
    if not re.fullmatch(r"[a-z][a-z0-9_]*\.py", factory["file"]) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", factory["function"]
    ):
        raise ValueError("Workflow factory must name a packaged module and function")
    files = manifest["files"]
    cache = Path(tempfile.mkdtemp(prefix="opencontracts-workflow-"))
    for name, expected in files.items():
        if not re.fullmatch(
            r"[a-z][a-z0-9_-]*\.(py|json|txt)", name
        ) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid workflow package file definition")
        path = cache / name
        path.write_bytes(verified(read(name), expected))
        path.chmod(0o600)
    if factory["file"] not in files:
        raise ValueError("Workflow response factory is missing from verified files")
    spec = importlib.util.spec_from_file_location(
        "workflow_" + package_hash, cache / factory["file"]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return manifest, getattr(module, factory["function"])


@lru_cache(maxsize=512)
def resolve_response_model(token):
    match = TOKEN.fullmatch(token)
    if not match:
        raise ValueError("Invalid installed workflow response definition")
    manifest, factory = package(match[1])
    column = match[2]
    if column not in {c["key"] for c in manifest["columns"]}:
        raise ValueError("Column is not defined by the installed workflow package")
    model = factory(column)
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise ValueError("Workflow factory must return a Pydantic response model")
    return model


@lru_cache(maxsize=32)
def resolve_label_policy(package_hash):
    """Load owner-approved label rules through the verified package boundary."""
    manifest, factory = package(package_hash)
    pointer = manifest.get("label_policy")
    if (
        not isinstance(pointer, dict)
        or pointer.get("format") != "opencontracts-label-policy.v1"
    ):
        raise ValueError("Workflow has no supported label policy")
    filename = pointer.get("file")
    if (
        filename not in manifest["files"]
        or not isinstance(filename, str)
        or not filename.endswith(".json")
    ):
        raise ValueError("Label policy must name a verified JSON package file")
    directory = Path(sys.modules[factory.__module__].__file__).parent
    policy = json.loads(
        verified((directory / filename).read_bytes(), manifest["files"][filename])
    )
    if policy.get("format") != pointer["format"] or not policy.get("version"):
        raise ValueError("Unsupported label policy format or missing version")
    approval = policy.get("owner_approval", {})
    if not approval.get("approved_on") or not approval.get("source"):
        raise ValueError("Label policy requires recorded owner approval")
    labels = {item["key"]: item for item in manifest["labels"]}
    if len(labels) != len(manifest["labels"]):
        raise ValueError("Workflow label keys must be unique")
    columns = {item["key"] for item in manifest["columns"]}

    def require_label(key, kind):
        if key not in labels or labels[key]["label_type"] != kind:
            raise ValueError("Label policy references an unknown or incompatible label")

    evidence = policy.get("evidence", {})
    if not isinstance(evidence.get("state_field"), str) or not evidence.get(
        "eligible_states"
    ):
        raise ValueError("Label evidence requires a state field and eligible states")
    if evidence.get("applicability_gate", False) is not False:
        raise ValueError("Label policy must not infer criterion applicability")
    if not isinstance(evidence.get("by_column"), dict):
        raise ValueError("Label evidence requires column mappings")
    for column, keys in evidence["by_column"].items():
        if column not in columns or not isinstance(keys, list) or not keys:
            raise ValueError("Label policy references an unknown column")
        for key in keys:
            require_label(key, "TOKEN_LABEL")
    for rule in policy.get("source_rules", []):
        if rule.get("kind") not in {"passage", "document"}:
            raise ValueError("Unknown source label rule kind")
        require_label(
            rule.get("label_key"),
            "TOKEN_LABEL" if rule["kind"] == "passage" else "DOC_TYPE_LABEL",
        )
        flags = rule.get("flags", [])
        if set(flags) - {"IGNORECASE", "MULTILINE", "DOTALL"}:
            raise ValueError("Unsupported source rule flags")
        re.compile(rule["pattern"], sum(getattr(re, flag) for flag in flags))
        if "max_line_tokens" in rule and (
            type(rule["max_line_tokens"]) is not int or rule["max_line_tokens"] < 1
        ):
            raise ValueError("Source rule line bound must be a positive integer")
    for rule in policy.get("finding_document_rules", []):
        require_label(rule.get("label_key"), "DOC_TYPE_LABEL")
        if (
            rule.get("column_key") not in columns
            or rule.get("match") not in {"equals", "contains_word"}
            or not isinstance(rule.get("state_field"), str)
            or not rule.get("eligible_states")
            or not isinstance(rule.get("value_path"), str)
            or not isinstance(rule.get("values"), list)
            or not all(isinstance(value, str) and value for value in rule["values"])
        ):
            raise ValueError("Invalid finding document label rule")
    for rule in policy.get("source_identity_rules", []):
        require_label(rule.get("label_key"), "DOC_TYPE_LABEL")
        if not isinstance(rule.get("kind"), str) or not rule["kind"]:
            raise ValueError("Source identity label rule requires a kind")
    return manifest, policy
