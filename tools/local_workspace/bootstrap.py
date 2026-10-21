"""Create the installation owner and install verified local workflow packages."""

import os
from pathlib import Path

import django


def main():
    django.setup()
    from django.contrib.auth import get_user_model

    from opencontractserver.documents.models import PipelineSettings
    from opencontractserver.extracts.definition_installer import install_definitions

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
    for manifest in Path(os.environ["WORKFLOW_PACKAGE_ROOT"]).glob("*/manifest.json"):
        install_definitions(manifest.parent.name, username)


if __name__ == "__main__":
    main()
