"""Small configuration contract shared by the controller and Git launcher."""

import json
import re
from pathlib import PurePosixPath
from urllib.parse import urlparse

CONFIGURATION_ENVIRONMENT = "INSTALLATION_CONFIG_JSON"
CONFIGURATION_NAMES = frozenset(
    {
        "APP_ORIGIN",
        "OPENCONTRACTS_SCHEMA",
        "OPENCONTRACTS_DATABASE_MODE",
        "PILOT_USERNAME",
        "WORKFLOW_PACKAGE_ROOT",
        "WORKFLOW_INSTALL_HASHES",
        "DATABRICKS_TOOL_STRICT",
    }
)


def validate_configuration(value, *, require_origin=True):
    if not isinstance(value, dict) or set(value) - CONFIGURATION_NAMES:
        raise ValueError("Installation configuration contains unsupported settings")
    if any(not isinstance(item, str) for item in value.values()):
        raise ValueError("Installation configuration values must be strings")
    if require_origin:
        origin = urlparse(value.get("APP_ORIGIN", ""))
        if (
            origin.scheme != "https"
            or not origin.netloc
            or origin.path
            or origin.query
            or origin.fragment
            or origin.username
        ):
            raise ValueError("Installation configuration needs an HTTPS App origin")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value.get("OPENCONTRACTS_SCHEMA", "")):
        raise ValueError(
            "Installation configuration needs a PostgreSQL schema identifier"
        )
    root = PurePosixPath(value.get("WORKFLOW_PACKAGE_ROOT", ""))
    if (
        not str(root).startswith("/Volumes/")
        or ".." in root.parts
        or len(root.parts) < 5
    ):
        raise ValueError("Installation configuration needs a workflow volume path")
    hashes = json.loads(value.get("WORKFLOW_INSTALL_HASHES", "[]"))
    if (
        not isinstance(hashes, list)
        or any(
            not isinstance(item, str) or not re.fullmatch(r"[0-9a-f]{64}", item)
            for item in hashes
        )
        or len(set(hashes)) != len(hashes)
    ):
        raise ValueError("Installation configuration needs distinct workflow hashes")
    if not value.get("PILOT_USERNAME"):
        raise ValueError("Installation configuration needs its retained owner username")
    if value.get("DATABRICKS_TOOL_STRICT", "preserve") not in ("preserve", "omit"):
        raise ValueError("Installation tool strict mode is unsupported")
    if value.get("OPENCONTRACTS_DATABASE_MODE", "owned") not in ("owned", "existing"):
        raise ValueError("Installation database mode must be owned or existing")
    return value


def load_environment(environment):
    encoded = environment.pop(CONFIGURATION_ENVIRONMENT, None)
    if encoded is not None:
        environment.update(validate_configuration(json.loads(encoded)))
