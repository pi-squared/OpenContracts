"""Exercise native admission and Celery tasks against an explicit QA installation.

The operator context verifies QA identity before loading Django. Controls create
their own rows; no existing document, extract, or finding is changed.
"""

import os
import runpy
import unittest
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(
    os.environ.get("OPENCONTRACTS_QA_CONTEXT"), "Explicit QA context required"
)
class ExtractionReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runpy.run_path(os.environ["OPENCONTRACTS_QA_CONTEXT"])
        from django.contrib.auth import get_user_model

        cls.user = get_user_model().objects.get(username="pilot-owner")

    def setUp(self):
        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.models import (
            Column,
            Datacell,
            Extract,
            Fieldset,
        )

        self.document = Document.objects.create(
            title="Readiness control",
            creator=self.user,
            processing_status="failed",
            processing_error="Synthetic parser failure",
            backend_lock=True,
        )
        self.fieldset = Fieldset.objects.create(
            name="Readiness control", creator=self.user
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Control",
            output_type="str",
            query="Find control",
            task_name="doc_extract_query_task",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            name="Readiness control", fieldset=self.fieldset, creator=self.user
        )
        self.extract.documents.add(self.document)
        self.cell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )
        # HTTP is the external provider boundary. Any attempted call fails the test.
        self.http = patch(
            "httpx.Client.send",
            side_effect=AssertionError("Model request on unavailable source"),
        )
        self.ahttp = patch(
            "httpx.AsyncClient.send",
            side_effect=AssertionError("Model request on unavailable source"),
        )
        self.calls = self.http.start()
        self.acalls = self.ahttp.start()
        self.addCleanup(self.http.stop)
        self.addCleanup(self.ahttp.stop)

    def tearDown(self):
        self.extract.delete()
        self.fieldset.delete()
        self.document.delete()

    def test_failed_document_is_rejected_by_graphql_without_starting(self):
        from graphql_relay import to_global_id

        from config.graphql.schema import schema

        result = schema.execute_sync(
            "mutation($id: ID!) { startExtract(extractId: $id) { ok message } }",
            variable_values={"id": to_global_id("ExtractType", self.extract.pk)},
            context_value=SimpleNamespace(user=self.user),
        )
        self.assertIsNone(result.errors)
        self.assertFalse(result.data["startExtract"]["ok"])
        self.assertIn("processing failed", result.data["startExtract"]["message"])
        self.extract.refresh_from_db()
        self.assertIsNone(self.extract.started)
        self.calls.assert_not_called()
        self.acalls.assert_not_called()

    def test_orchestration_fails_before_creating_rows_or_dispatching_fields(self):
        from opencontractserver.tasks.extract_orchestrator_tasks import run_extract

        run_extract.run(self.extract.pk, self.user.pk)
        self.extract.refresh_from_db()
        self.assertIn("processing failed", self.extract.error)
        self.assertIsNone(self.extract.started)
        self.calls.assert_not_called()
        self.acalls.assert_not_called()

    def test_queued_field_fails_without_an_answer_or_provider_request(self):
        from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

        with self.assertRaisesRegex(ValueError, "processing failed"):
            doc_extract_query_task.run(self.cell.pk)
        self.cell.refresh_from_db()
        self.assertIsNotNone(self.cell.failed)
        self.assertIsNone(self.cell.completed)
        self.assertIn("processing failed", self.cell.stacktrace)
        self.assertEqual(self.cell.data, {})
        self.calls.assert_not_called()
        self.acalls.assert_not_called()

    def test_completed_lifecycle_without_text_is_still_rejected(self):
        from databricks_port.extraction_readiness import ensure_document_ready

        self.document.processing_status = "completed"
        self.document.backend_lock = False
        self.document.save(update_fields=["processing_status", "backend_lock"])
        with self.assertRaisesRegex(ValueError, "text is unavailable"):
            ensure_document_ready(self.document)

    def test_index_is_required_for_each_retained_passage(self):
        import uuid

        from databricks_port.extraction_readiness import ensure_document_ready

        from opencontractserver.annotations.models import (
            Annotation,
            StructuralAnnotationSet,
        )
        from opencontractserver.documents.models import Document

        source = Document.objects.filter(
            processing_status="completed",
            txt_extract_file__gt="",
            structural_annotation_set__isnull=False,
        ).first()
        self.assertIsNotNone(source, "QA needs its existing processed public source")
        structural = StructuralAnnotationSet.objects.create(
            content_hash=uuid.uuid4().hex, creator=self.user
        )
        self.document.processing_status = "completed"
        self.document.backend_lock = False
        self.document.file_type = source.file_type
        self.document.page_count = source.page_count
        self.document.txt_extract_file = source.txt_extract_file.name
        self.document.pawls_parse_file = source.pawls_parse_file.name
        self.document.structural_annotation_set = structural
        self.document.save()
        Annotation.objects.create(
            structural=True,
            structural_set=structural,
            raw_text="Unindexed control",
            creator=self.user,
        )
        try:
            with self.assertRaisesRegex(ValueError, "retrieval index is incomplete"):
                ensure_document_ready(self.document)
            self.calls.assert_not_called()
            self.acalls.assert_not_called()
        finally:
            self.document.structural_annotation_set = None
            self.document.save(update_fields=["structural_annotation_set"])
            structural.delete()

    def test_existing_complete_indexed_qa_source_is_ready(self):
        from databricks_port.extraction_readiness import ensure_document_ready

        from opencontractserver.documents.models import Document

        source = Document.objects.filter(
            processing_status="completed",
            txt_extract_file__gt="",
            structural_annotation_set__isnull=False,
        ).first()
        self.assertIsNotNone(source, "QA needs its existing processed public source")
        ensure_document_ready(source)
        self.calls.assert_not_called()
        self.acalls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
