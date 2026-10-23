"""GH-5: portable Terms validation through a new native extraction.

Requires the private input handoff via TERMS_INPUT_HANDOFF. The deterministic
FunctionModel exercises retries; it is not an evaluation of a served model.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase
from django.utils import timezone
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.extracts.workflows import resolve_response_model
from opencontractserver.pipeline.parsers.native_pdf import parse_native_pdf
from opencontractserver.tasks.data_extract_tasks import doc_extract_query_task

CANDIDATE = "a74d6ea925b688edf9ec5c8465b298f983bdae2b403d804a3816e270fbb6d2ac"


@skipUnless(
    os.environ.get("TERMS_INPUT_HANDOFF"),
    "Private GH-5 inputs required; see docs/issue-5/README.md",
)
class PartyBlankWorkflowTests(TransactionTestCase):
    def setUp(self):
        handoff = Path(os.environ["TERMS_INPUT_HANDOFF"])
        fixture_dir = handoff / "fixtures/issue-5"
        self.fixture = json.loads(
            (fixture_dir / "recovered-party-details.json").read_text()
        )
        pdf = (fixture_dir / "original.pdf").read_bytes()
        self.assertEqual(
            hashlib.sha256(pdf).hexdigest(), self.fixture["source"]["sha256"]
        )
        parsed = parse_native_pdf(pdf, title=self.fixture["source"]["title"])
        self.assertEqual(parsed["page_count"], 8)
        self.user = get_user_model().objects.create_user(username="blank-regression")
        self.doc = Document.objects.create(
            title=parsed["title"],
            creator=self.user,
            file_type="application/pdf",
            page_count=8,
            backend_lock=False,
            processing_status="completed",
            processing_started=timezone.now(),
            pdf_file=ContentFile(pdf, name="recovered.pdf"),
            txt_extract_file=ContentFile(
                parsed["content"].encode(), name="recovered.txt"
            ),
            pawls_parse_file=ContentFile(
                json.dumps(parsed["pawls_file_content"]).encode(), name="recovered.json"
            ),
        )
        self.corpus = Corpus.objects.create(title="GH-5 local", creator=self.user)
        self.fieldset = Fieldset.objects.create(
            name="Terms regression", description="local", creator=self.user
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            creator=self.user,
            name="Party names and addresses",
            query="Assess the names and addresses of every party.",
            instructions=self.fixture["effective_instructions"],
            output_type=f"workflow:{CANDIDATE}:{self.fixture['criterion_key']}",
        )
        self.model = resolve_response_model(self.column.output_type)

    def cell(self, **kwargs):
        extract = Extract.objects.create(
            name="Local GH-5",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
            started=timezone.now(),
            finished=timezone.now(),
        )
        extract.documents.add(self.doc)
        return Datacell.objects.create(
            extract=extract,
            column=self.column,
            document=self.doc,
            creator=self.user,
            data_definition=self.column.output_type,
            **kwargs,
        )

    def test_retained_original_is_accepted_only_by_its_historical_package(self):
        original = copy.deepcopy(self.fixture["original_response"])
        baseline = resolve_response_model(self.fixture["workflow_definition"])
        self.assertEqual(baseline.model_validate(original).model_dump(), original)
        with self.assertRaises(ValidationError) as rejected:
            self.model.model_validate(original)
        self.assertEqual(
            rejected.exception.errors()[0]["type"], "blank_field_precedence"
        )
        self.assertIn(
            "even when other required details are not found", str(rejected.exception)
        )
        self.assertEqual(original, self.fixture["original_response"])

    def test_new_native_assessment_preserves_retry_and_historical_review(self):
        original = copy.deepcopy(self.fixture["original_response"])
        historical = self.cell(
            data={"data": original},
            corrected_data={"finding": "uncertain"},
            approved_by=self.user,
            completed=timezone.now(),
            llm_call_log="retained original log",
        )
        before = Datacell.objects.filter(pk=historical.pk).values().get()
        completed_run = Extract.objects.filter(pk=historical.extract_id).values().get()
        revised = {
            **original,
            "finding": "present_blank",
            "rationale": (
                "The lender details are populated, but the required hirer name/address fields "
                "are unpopulated. The selected field evidence establishes present_blank even "
                "where another required party detail was not found."
            ),
        }
        calls = []

        def respond(messages, info):
            calls.append(copy.deepcopy(messages))
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        info.output_tools[0].name,
                        original if len(calls) == 1 else revised,
                    )
                ]
            )

        async def assessment(**kwargs):
            self.assertIs(kwargs["target_type"], self.model)
            self.assertIn(self.fixture["effective_instructions"], kwargs["prompt"])
            result = await Agent(
                FunctionModel(respond),
                output_type=kwargs["target_type"],
                retries={"output": 2},
            ).run(kwargs["prompt"])
            return result.output, []

        new = self.cell()
        with patch(
            "opencontractserver.extracts.services.source_readiness.aensure_document_ready",
            new=AsyncMock(),
        ), patch(
            "opencontractserver.llms.agents",
            SimpleNamespace(
                get_structured_response_and_sources_from_document=assessment
            ),
        ):
            doc_extract_query_task.si(new.pk).apply(throw=True)
        new.refresh_from_db()
        self.assertIsNone(new.failed, new.stacktrace)
        self.assertIsNotNone(new.completed)
        self.assertEqual(new.data, {"data": revised})
        from opencontractserver.extracts.services.quotation_evidence import (
            finding_evidence,
        )

        anchors = finding_evidence(new)
        self.assertTrue(any(item.get("annotationId") for item in anchors), anchors)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(len(calls), 2)
        retries = [
            part
            for msg in calls[1]
            for part in msg.parts
            if isinstance(part, RetryPromptPart)
        ]
        self.assertTrue(
            any("blank_field_precedence" in str(part.content) for part in retries)
        )
        logged_submissions = [
            part.args_as_dict()
            for message in ModelMessagesTypeAdapter.validate_json(new.llm_call_log)
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        self.assertEqual(logged_submissions, [original, revised])
        self.assertEqual(
            Datacell.objects.filter(pk=historical.pk).values().get(), before
        )
        self.assertEqual(
            Extract.objects.filter(pk=historical.extract_id).values().get(),
            completed_run,
        )

    def test_five_outcome_controls_and_placeholder_precedence(self):
        original = self.fixture["original_response"]
        for finding, state in [
            ("present_blank", "present_blank"),
            ("contradicted", "present_blank"),
            ("supported", "populated"),
            ("not_found", "unclear"),
            ("uncertain", "unclear"),
        ]:
            with self.subTest(finding=finding):
                value = {**original, "finding": finding, "template_field_state": state}
                if finding in {"not_found", "uncertain"}:
                    value["evidence"] = []
                validated = self.model.model_validate(value).model_dump()
                saved = self.cell(data={"data": validated}, completed=timezone.now())
                saved.refresh_from_db()
                self.assertEqual(saved.data, {"data": value})
        for quote in ["Hirer name: ______", "Hirer address: [insert address]"]:
            value = {**original, "evidence": [{"quote": quote, "page": 1}]}
            with self.assertRaises(ValidationError):
                self.model.model_validate(value)
