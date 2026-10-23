"""Create the installation owner and install verified local workflow packages."""

import json
import os
from pathlib import Path

import django


def install_workspace_workflows(username):
    from opencontractserver.extracts.definition_installer import (
        DefinitionDriftError,
        install_definitions,
    )
    from opencontractserver.extracts.models import InstalledWorkflowPackage
    from opencontractserver.extracts.workflows import package

    # Bootstrap is also callable from local tools. Recheck immutable bytes even
    # if this process has loaded the package previously.
    package.cache_clear()
    report = []
    for manifest in Path(os.environ["WORKFLOW_PACKAGE_ROOT"]).glob("*/manifest.json"):
        identity = manifest.parent.name
        package(identity)
        registered = InstalledWorkflowPackage.objects.filter(
            package_hash=identity, owner__username=username
        ).exists()
        try:
            install_definitions(identity, username, verify_only=registered)
        except DefinitionDriftError as error:
            # Valid UI edits remain usable without overwriting them or claiming
            # they still reproduce the original definitions. Source/provenance
            # failures retain their strict exceptions and are never suppressed.
            report.append(
                {"package_hash": identity, "status": "edited", "reason": str(error)}
            )
        else:
            report.append(
                {
                    "package_hash": identity,
                    "status": "verified" if registered else "installed",
                }
            )
    return report


def main():
    django.setup()
    from django.contrib.auth import get_user_model

    from opencontractserver.documents.models import PipelineSettings

    username = os.environ["LOCAL_OWNER_USERNAME"]
    user, _ = get_user_model().objects.get_or_create(
        username=username,
        defaults={
            "email": username + "@localhost.invalid",
            "is_staff": True,
            "is_superuser": True,
        },
    )
    user.set_password(os.environ["LOCAL_OWNER_PASSWORD"])
    user.save()
    pipeline = PipelineSettings.get_instance()
    parsers = dict(pipeline.preferred_parsers or {})
    if parsers.get("application/pdf") in {
        None,
        "opencontractserver.pipeline.parsers.pymupdf_parser.PyMuPDFParser",
    }:
        parsers["application/pdf"] = (
            "opencontractserver.pipeline.parsers.warp_ingest_parser.WarpIngestParser"
        )
        pipeline.preferred_parsers = parsers
        pipeline.save()
    report = install_workspace_workflows(username)
    path = Path(os.environ["LOCAL_WORKSPACE_STATE"]) / "bootstrap-report.json"
    path.write_text(json.dumps({"workflows": report}, indent=2) + "\n")
    path.chmod(0o600)


if __name__ == "__main__":
    main()
