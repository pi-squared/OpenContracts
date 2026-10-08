"""Native PDF parser backed by a resource-bound Docling Databricks job."""

import hashlib
import os
from dataclasses import dataclass, field

from databricks_port.docling_jobs import (
    VERSION,
    DoclingJobError,
    encoded,
    new_attempt,
    parse_job,
)
from databricks_port.lakebase import workspace
from django.db import connection, transaction

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.utils.structural_sets import create_structural_annotation_set


class DoclingJobParser(BaseParser):
    title = "Docling · Databricks Job"
    description = "Parses PDFs on Databricks compute and retains original-PDF evidence."
    author = "OpenContracts Databricks port"
    supported_file_types = [FileTypeEnum.PDF]
    dependencies = ["databricks-sdk"]

    @dataclass
    class Settings:
        do_ocr: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL, description="Enable Docling OCR"
                )
            },
        )
        do_table_structure: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Retain Docling table structure",
                )
            },
        )

    def process_document(self, user_id, doc_id, **kwargs):
        # One parser/persistence owner per document, including after a restart.
        # A session advisory lock releases when the worker connection closes.
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s,%s)", [132980, doc_id])
            if not cursor.fetchone()[0]:
                raise DocumentParsingError(
                    "This Docling source is already processing", is_transient=False
                )
        try:
            document = Document.objects.get(pk=doc_id)
            if document.structural_annotation_set_id:
                identity = document.custom_meta or {}
                retained = document.structural_annotation_set
                if (
                    retained.parser_name == self.title
                    and retained.content_hash == identity.get("parsing_artifact_sha256")
                ):
                    # Parse persistence already completed before interruption;
                    # continue the native remap/unlock steps without duplicating it.
                    return {}
                raise DocumentParsingError(
                    "Existing source evidence must be preserved", is_transient=False
                )
            return super().process_document(user_id, doc_id, **kwargs)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s,%s)", [132980, doc_id])

    def _parse_document_impl(self, user_id, doc_id, **kwargs):
        document = Document.objects.get(pk=doc_id)
        with document.pdf_file.open("rb") as original:
            source = original.read()
        job_id = os.environ.get("DOCLING_JOB_ID")
        root = os.environ.get("DOCLING_ARTIFACT_ROOT")
        if not job_id or not root:
            raise DocumentParsingError(
                "Configure the Docling job and artifact volume resources",
                is_transient=False,
            )
        options = {
            key: bool(kwargs.get(key, True)) for key in ("do_ocr", "do_table_structure")
        }

        def persist(attempt):
            with transaction.atomic():
                fresh = Document.objects.select_for_update().get(pk=doc_id)
                fresh.custom_meta = {
                    **(fresh.custom_meta or {}),
                    "docling_job": attempt,
                }
                fresh.save(update_fields=["custom_meta"])

        attempt = (document.custom_meta or {}).get("docling_job")
        if attempt is None:
            attempt = new_attempt(source, job_id, root, document.title, options)
            persist(attempt)
        elif attempt["options"] != options:
            raise DocumentParsingError(
                "Retained Docling attempt settings changed; use a fresh source",
                is_transient=False,
            )
        try:
            export, receipt = parse_job(source, attempt, persist, workspace())
        except DoclingJobError as error:
            raise DocumentParsingError(str(error), is_transient=False) from error
        document.refresh_from_db()
        identity = {
            "parser": self.title,
            "parser_version": VERSION,
            "source_sha256": attempt["source_sha256"],
            "export_sha256": receipt["export_sha256"],
            "attempt_id": attempt["attempt_id"],
            "job_id": attempt["job_id"],
            "run_id": attempt["run_id"],
            "configuration": receipt["pipeline_options"],
            "geometry_resolution": "Docling paragraph/table rectangles; no manufactured word boxes",
        }
        identity["parsing_artifact_sha256"] = hashlib.sha256(
            encoded(identity)
        ).hexdigest()
        document.custom_meta = {**(document.custom_meta or {}), **identity}
        document.save(update_fields=["custom_meta"])
        return export

    def _create_structural_annotation_set(self, document, user):
        create_structural_annotation_set(
            document,
            user,
            parser_name=self.title,
            parser_version=VERSION,
            artifact_identity=document.custom_meta["parsing_artifact_sha256"],
        )

    def save_parsed_data(self, *args, **kwargs):
        # Commit the complete annotation set together. Recovery must not accept
        # a structural-set marker belonging to a partially imported export.
        with transaction.atomic():
            return super().save_parsed_data(*args, **kwargs)
