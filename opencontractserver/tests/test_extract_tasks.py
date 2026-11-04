"""
Quick test for the new structured extraction implementation (synchronous version).
"""

from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase

from opencontractserver.annotations.models import Embedding
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.extracts.services.source_readiness import SourceNotReady
from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.tests.extraction_fixtures import (
    fake_structured_response,
    prepare_extraction_source,
    replay_extraction,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class NewExtractionTestCase(TransactionTestCase):
    """Test the new agent-based extraction pipeline (sync)."""

    # Set by the replay decorator as a spy on the real AgentAPI method.
    agent: AsyncMock

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create document
        self.document = Document.objects.create(
            title="Test Document", creator=self.user, file_type="text/plain"
        )
        self.document, _, _ = self.corpus.add_document(
            document=self.document, user=self.user
        )
        prepare_extraction_source(
            self.document,
            self.corpus,
            text="Test Document. Payment terms: payment is due in thirty days.",
        )

        # Create fieldset
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test extraction fields",
            creator=self.user,
        )

    @replay_extraction("test_simple_string_extraction.yaml", expected_interactions=1)
    def test_simple_string_extraction(self):
        """Test extracting a simple string value."""
        # Create column
        column = Column.objects.create(
            name="Document Title",
            fieldset=self.fieldset,
            query="What is the title of this document?",
            output_type="str",
            extract_is_list=False,
            creator=self.user,
        )

        # Create extract
        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )

        extract.documents.add(self.document)

        # Create datacell
        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply(throw=True)

        datacell.refresh_from_db()

        completed = datacell.completed
        failed = datacell.failed
        data = datacell.data

        assert completed is not None
        assert failed is None
        assert data is not None
        assert "data" in data
        self.agent.assert_awaited_once()
        call = self.agent.await_args_list[0]
        self.assertEqual(call.kwargs["document"], self.document.pk)
        self.assertEqual(call.kwargs["corpus"], self.corpus.pk)

    @replay_extraction("test_list_extraction.yaml", expected_interactions=1)
    def test_list_extraction(self):
        """Test extracting a list of values."""
        column = Column.objects.create(
            name="Key Terms",
            fieldset=self.fieldset,
            query="List all the key terms mentioned in this document",
            output_type="str",
            extract_is_list=True,
            creator=self.user,
        )

        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )
        extract.documents.add(self.document)

        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="list[str]",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply(throw=True)

        datacell.refresh_from_db()

        completed = datacell.completed
        data = datacell.data

        assert completed is not None
        assert data is not None
        assert isinstance(data.get("data"), list)
        self.agent.assert_awaited_once()

    @replay_extraction("test_with_constraints.yaml", expected_interactions=1)
    def test_with_constraints(self):
        """Test extraction with must_contain_text and limit_to_label."""
        column = Column.objects.create(
            name="Payment Terms",
            fieldset=self.fieldset,
            query="What are the payment terms?",
            output_type="str",
            must_contain_text="payment",
            limit_to_label="contract_clause",
            instructions="Focus on payment schedules and amounts",
            creator=self.user,
        )

        extract = Extract.objects.create(
            name="Test Extract", fieldset=self.fieldset, creator=self.user
        )
        extract.documents.add(self.document)

        datacell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )

        # Run extraction
        doc_extract_query_task.si(datacell.id).apply(throw=True)

        datacell.refresh_from_db()

        started = datacell.started
        failed = datacell.failed
        completed = datacell.completed

        # Should complete (might return None if constraints not met)
        assert started is not None
        assert failed is None or completed is not None
        self.agent.assert_awaited_once()

    def _source_readiness_cell(self):
        column = Column.objects.create(
            name="Source readiness",
            fieldset=self.fieldset,
            query="What is the title?",
            output_type="str",
            creator=self.user,
        )
        extract = Extract.objects.create(
            name="Source gate",
            fieldset=self.fieldset,
            creator=self.user,
        )
        extract.documents.add(self.document)
        return Datacell.objects.create(
            extract=extract,
            column=column,
            document=self.document,
            data_definition="str",
            creator=self.user,
        )

    def _assert_source_rejected(self, reason):
        cell = self._source_readiness_cell()
        with patch(
            "opencontractserver.llms.api.AgentAPI.get_structured_response_and_sources_from_document",
            new_callable=AsyncMock,
            side_effect=fake_structured_response,
        ) as agent:
            with self.assertRaisesRegex(SourceNotReady, reason):
                doc_extract_query_task.si(cell.id).apply(throw=True)
            agent.assert_not_awaited()
        cell.refresh_from_db()
        self.assertIsNotNone(cell.failed)
        self.assertIsNone(cell.completed)

    def test_incomplete_source_cannot_call_agent(self):
        self.document.processing_status = "pending"
        self.document.save(update_fields=["processing_status"])
        self._assert_source_rejected("processing is incomplete")

    def test_empty_source_cannot_call_agent(self):
        self.document.txt_extract_file.save("empty-source.txt", ContentFile(b""))
        self._assert_source_rejected("text is empty")

    def test_unindexed_source_cannot_call_agent(self):
        Embedding.objects.filter(annotation__document=self.document).delete()
        self._assert_source_rejected("index is incomplete")


class ExtractOrchestrationTestCase(TransactionTestCase):
    """Test the extract orchestration pipeline."""

    # Set by the replay decorator as a spy on the real AgentAPI method.
    agent: AsyncMock

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create corpus
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)

        # Create multiple documents
        self.doc1 = Document.objects.create(
            title="Test Document 1",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 1 content with payment terms"
            ),
        )
        self.doc2 = Document.objects.create(
            title="Test Document 2",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 2 content with delivery terms"
            ),
        )
        self.doc3 = Document.objects.create(
            title="Test Document 3",
            creator=self.user,
            file_type="text/plain",
            txt_extract_file=self._create_txt_file(
                "Document 3 content with warranty terms"
            ),
        )

        # Add documents to corpus
        self.doc1, _, _ = self.corpus.add_document(document=self.doc1, user=self.user)
        self.doc2, _, _ = self.corpus.add_document(document=self.doc2, user=self.user)
        self.doc3, _, _ = self.corpus.add_document(document=self.doc3, user=self.user)
        for document in (self.doc1, self.doc2, self.doc3):
            prepare_extraction_source(document, self.corpus)

        # Create fieldset with multiple columns
        self.fieldset = Fieldset.objects.create(
            name="Contract Terms Fieldset",
            description="Extract key contract terms",
            creator=self.user,
        )

        # Create columns for different data types
        self.title_column = Column.objects.create(
            name="Document Title",
            fieldset=self.fieldset,
            query="What is the title of this document?",
            output_type="str",
            extract_is_list=False,
            creator=self.user,
        )

        self.terms_column = Column.objects.create(
            name="Key Terms",
            fieldset=self.fieldset,
            query="List all important terms mentioned in this document",
            output_type="str",
            extract_is_list=True,
            creator=self.user,
        )

        self.has_payment_column = Column.objects.create(
            name="Has Payment Terms",
            fieldset=self.fieldset,
            query="Does this document contain payment terms?",
            output_type="bool",
            extract_is_list=False,
            must_contain_text="payment",
            creator=self.user,
        )

    def _create_txt_file(self, content):
        """Helper to create a simple text file for testing."""
        from django.core.files.base import ContentFile

        return ContentFile(content.encode("utf-8"), name="test.txt")

    @replay_extraction("test_run_extract_orchestration.yaml", expected_interactions=9)
    def test_run_extract_orchestration(self):
        """Test the full extract orchestration with multiple documents and columns."""
        # Create extract
        extract = Extract.objects.create(
            name="Test Full Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])

        # Add all documents
        extract.documents.add(self.doc1, self.doc2, self.doc3)

        # Get initial datacell count
        # initial_datacell_count = extract.extracted_datacells.count()

        # Run the orchestration task
        run_extract.si(extract.id, self.user.id).apply()

        # Refresh extract
        extract.refresh_from_db()

        # Verify extract was marked as started
        assert extract.started is not None
        self.assertEqual(self.agent.await_count, 9)

        # Verify correct number of datacells created
        # Should be: 3 documents × 3 columns = 9 datacells
        expected_count = len(extract.documents.all()) * len(self.fieldset.columns.all())
        actual_count = extract.extracted_datacells.count()

        assert (
            actual_count == expected_count
        ), f"Expected {expected_count} datacells, got {actual_count}"

        # Verify all datacells are associated correctly
        for doc in extract.documents.all():
            for column in self.fieldset.columns.all():
                datacell_exists = extract.extracted_datacells.filter(
                    document=doc, column=column
                ).exists()
                assert (
                    datacell_exists
                ), f"Missing datacell for doc {doc.title} and column {column.name}"

    @replay_extraction("test_new_extract_orchestration.yaml", expected_interactions=3)
    def test_extract_with_vcr(self):
        """Replay the recorded SDK responses through single-document orchestration."""

        # Create a simple extract
        extract = Extract.objects.create(
            name="VCR Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])
        extract.documents.add(self.doc1)  # Just one doc for VCR test

        # Run extraction; the decorator forbids any new provider recording.
        run_extract.si(extract.id, self.user.id).apply()

        # Verify datacells were created
        assert extract.extracted_datacells.count() == len(self.fieldset.columns.all())

    @patch(
        "opencontractserver.llms.api.AgentAPI.get_structured_response_and_sources_from_document",
        new_callable=AsyncMock,
        side_effect=fake_structured_response,
    )
    def test_extract_completion_callback(self, agent):
        """Test that the extract completion callback is properly called."""
        from unittest.mock import patch

        extract = Extract.objects.create(
            name="Callback Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])
        extract.documents.add(self.doc1)

        # In eager mode (test environment), mark_extract_complete is called directly.
        # We patch it to verify it gets called with the correct extract_id.
        with patch(
            "opencontractserver.tasks.extract_orchestrator_tasks.mark_extract_complete"
        ) as mock_callback:
            run_extract.si(extract.id, self.user.id).apply()

            # Verify the completion callback was called with correct extract_id
            mock_callback.assert_called_once_with(extract.id)

            # Verify the extract was started
            extract.refresh_from_db()
            assert extract.started is not None
            self.assertEqual(agent.await_count, 3)

    @patch(
        "opencontractserver.llms.api.AgentAPI.get_structured_response_and_sources_from_document",
        new_callable=AsyncMock,
        side_effect=fake_structured_response,
    )
    def test_run_extract_aborts_for_nonexistent_user(self, agent):
        """run_extract should abort silently when user_id doesn't exist."""
        extract = Extract.objects.create(
            name="Abort Test Extract", fieldset=self.fieldset, creator=self.user
        )
        set_permissions_for_obj_to_user(self.user, extract, [PermissionTypes.ALL])

        # Use an ID that doesn't exist
        nonexistent_user_id = 999999

        # Should not raise — just return early
        run_extract.si(extract.id, nonexistent_user_id).apply()

        # Extract should NOT have a started timestamp (task aborted before setting it)
        extract.refresh_from_db()
        self.assertIsNone(extract.started)
        agent.assert_not_awaited()

    @patch(
        "opencontractserver.llms.api.AgentAPI.get_structured_response_and_sources_from_document",
        new_callable=AsyncMock,
        side_effect=fake_structured_response,
    )
    def test_run_extract_aborts_for_unauthorized_user(self, agent):
        """run_extract should abort when user lacks UPDATE permission."""
        # Create a different user with no permissions on the extract
        other_user = User.objects.create_user(
            username="noperm_user", password="testpass123"
        )

        extract = Extract.objects.create(
            name="Permission Test Extract", fieldset=self.fieldset, creator=self.user
        )
        # Don't grant permissions to other_user

        run_extract.si(extract.id, other_user.id).apply()

        # Extract should NOT have a started timestamp (task aborted)
        extract.refresh_from_db()
        self.assertIsNone(extract.started)
        agent.assert_not_awaited()

    @patch(
        "opencontractserver.llms.api.AgentAPI.get_structured_response_and_sources_from_document",
        new_callable=AsyncMock,
        side_effect=fake_structured_response,
    )
    def test_run_extract_aborts_for_none_extract_id(self, agent):
        """run_extract returns early when extract_id is None (PR #1482 typing fix)."""
        # Should not raise — guard at the top of the task aborts before any DB hit.
        result = run_extract.si(None, self.user.id).apply()

        # Eager-mode return value must be None (the guard ``return`` clause).
        self.assertIsNone(result.result)
        agent.assert_not_awaited()
