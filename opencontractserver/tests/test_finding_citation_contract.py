"""Future findings through real PDF projection, persistence and the native API.

Requires isolated PostgreSQL with pgvector. No model, embedder or parser calls.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import RequestFactory, TestCase

from config.graphql.schema import schema
from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.extracts.services.quotation_evidence import (
    finding_evidence,
    finding_sources,
)
from opencontractserver.tests.test_extraction_grounding import _build_pawls_for_text
from opencontractserver.utils.ids import to_global_id


class FindingCitationContractTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory(prefix="gh8-native-media-")
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.user = get_user_model().objects.create_user(username="future-citations")
        self.corpus = Corpus.objects.create(
            title="Future citation fixtures", creator=self.user
        )
        self.document = Document.objects.create(
            title="Deterministic PDF text",
            file_type="application/pdf",
            page_count=3,
            creator=self.user,
        )
        self.fieldset = Fieldset.objects.create(name="Citations", creator=self.user)
        self.column = Column.objects.create(
            name="Quotation",
            fieldset=self.fieldset,
            query="fixture",
            output_type="object",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            name="Future fixtures",
            corpus=self.corpus,
            fieldset=self.fieldset,
            creator=self.user,
        )

    def cell(self, pages, reported, quote="selected words"):
        self.document.pawls_parse_file.save(
            "future.pawls", ContentFile(_build_pawls_for_text(pages).encode())
        )
        return Datacell.objects.create(
            document=self.document,
            extract=self.extract,
            column=self.column,
            creator=self.user,
            data={
                "finding": "supported",
                "evidence": [{"quote": quote, "page": reported}],
            },
        )

    def api(self, cell):
        request = RequestFactory().post("/graphql/")
        request.user = self.user
        response = schema.execute_sync(
            """query($id: ID!) { datacell(id: $id) {
              id data correctedData findingEvidence fullSourceList {
                id page rawText json annotationType isEvidenceQuote structural
                annotationLabel { id text color labelType }
                document { id slug creator { id slug } }
                corpus { id slug creator { id slug } }
              }
            }}""",
            variable_values={"id": to_global_id("DatacellType", cell.pk)},
            context_value=request,
        )
        self.assertIsNone(response.errors, response.errors)
        assert response.data is not None
        self.assertIsNotNone(response.data["datacell"])
        return response.data["datacell"]

    def test_behavior_table_new_findings_and_api_navigation(self):
        cases = [
            (["selected words", "selected words"], 2, "matched", 2),
            (["cover", "selected words selected words"], 2, "ambiguous", None),
            (["cover", "selected words"], 1, "different_page", 2),
            (["cover", "selected words", "selected words"], 1, "ambiguous", None),
            (["cover", "selected words"], None, "matched", 2),
            (["selected words", "selected words"], None, "ambiguous", None),
            (["cover", "selected"], 2, "unmatched", None),
        ]
        for pages, reported, status, located in cases:
            with self.subTest(reported=reported, pages=pages):
                cell = self.cell(pages, reported)
                self.assertFalse(cell.evidence_anchors)
                result = self.api(cell)
                (anchor,) = result["findingEvidence"]
                self.assertEqual(
                    (anchor["status"], anchor["locatedPage"]), (status, located)
                )
                self.assertEqual(anchor["reportedPage"], reported)
                self.assertEqual(result["data"], cell.data)
                sources = list(finding_sources(cell))
                if located is None:
                    self.assertEqual(sources, [])
                    self.assertEqual(result["fullSourceList"], [])
                    self.assertIsNone(anchor["annotationId"])
                    continue
                (annotation,) = sources
                self.assertEqual(annotation.page, located - 1)
                self.assertEqual(annotation.raw_text, "selected words")
                self.assertEqual(annotation.document_id, self.document.pk)
                self.assertEqual(annotation.corpus_id, self.corpus.pk)
                (page,) = list(iter_page_annotations(annotation.json))
                self.assertEqual(page.page_index, located - 1)
                self.assertEqual(page.token_indices, [0, 1])
                # PlasmaPDF pads the complete token bounds by five percent.
                for side, expected in {
                    "left": 5.9,
                    "right": 96.1,
                    "top": 99.4,
                    "bottom": 112.6,
                }.items():
                    self.assertAlmostEqual(page.bounds[side], expected)
                (source,) = result["fullSourceList"]
                self.assertEqual(source["id"], anchor["annotationId"])
                self.assertEqual(source["page"], located - 1)
                self.assertEqual(
                    source["document"]["id"],
                    to_global_id("DocumentType", self.document.pk),
                )
                self.assertEqual(source["json"], annotation.json)

    def test_corrected_finding_keeps_original_and_other_findings(self):
        cell = self.cell(["selected words", "distinct selected words"], 1)
        original = self.api(cell)
        other = Datacell.objects.create(
            document=self.document,
            extract=self.extract,
            column=self.column,
            creator=self.user,
            data=cell.data,
        )
        other_evidence = finding_evidence(other)
        cell.corrected_data = {
            "finding": "supported",
            "evidence": [{"quote": "distinct selected words", "page": None}],
        }
        cell.save(update_fields=["corrected_data"])
        corrected = self.api(cell)
        self.assertEqual(corrected["data"], original["data"])
        (anchor,) = corrected["findingEvidence"]
        self.assertEqual((anchor["status"], anchor["locatedPage"]), ("matched", 2))
        self.assertEqual(
            corrected["fullSourceList"][0]["rawText"], "distinct selected words"
        )
        self.assertNotEqual(
            anchor["annotationId"], original["findingEvidence"][0]["annotationId"]
        )
        cell.refresh_from_db()
        self.assertEqual(set(cell.evidence_anchors), {"original", "corrected"})
        self.assertEqual(finding_evidence(other), other_evidence)
        self.assertFalse(cell.approved_by_id)
        self.assertFalse(cell.rejected_by_id)

    def test_incomplete_projection_is_not_navigable(self):
        cell = self.cell(["selected words"], 1)
        with patch(
            "opencontractserver.utils.span_projection.project_span_to_token_annotation",
            return_value=({}, 0, "selected"),
        ):
            (anchor,) = finding_evidence(cell)
        self.assertEqual(anchor["status"], "projection_unavailable")
        self.assertIsNone(anchor["annotationId"])
        self.assertFalse(cell.sources.exists())

    def test_unavailable_source_has_no_highlight(self):
        cell = self.cell(["selected words"], None)
        self.document.pawls_parse_file.delete()
        (anchor,) = self.api(cell)["findingEvidence"]
        self.assertEqual(anchor["status"], "source_unavailable")
        self.assertIsNone(anchor["annotationId"])

    def test_public_pdf_future_findings_for_local_browser(self):
        import pymupdf

        public_pdf = (
            Path(__file__).resolve().parents[2]
            / "frontend/tests/fixtures/usc-title-1.pdf"
        )
        with pymupdf.open(public_pdf) as pdf:
            pawls = [
                {
                    "page": {
                        "index": index,
                        "width": page.rect.width,
                        "height": page.rect.height,
                    },
                    "tokens": [
                        {
                            "x": x0,
                            "y": y0,
                            "width": x1 - x0,
                            "height": y1 - y0,
                            "text": word,
                        }
                        for x0, y0, x1, y1, word, *_ in page.get_text("words")
                    ],
                }
                for index, page in enumerate(pdf)
            ]
        self.document.page_count = len(pawls)
        self.document.save(update_fields=["page_count"])
        self.document.pawls_parse_file.save(
            "public.pawls", ContentFile(json.dumps(pawls).encode())
        )
        unique = "words importing the singular include and apply to several persons"
        cases = [
            ("unique", unique, 3, "matched", 3),
            ("no-page", unique, None, "matched", 3),
            ("discrepancy", unique, 1, "different_page", 3),
            ("cross-page", "STATUTORY NOTES AND RELATED SUBSIDIARIES", 1, "matched", 1),
            ("same-page", "July 30, 1947", 1, "ambiguous", None),
        ]
        fixtures = []
        for name, quote, reported, status, located in cases:
            cell = Datacell.objects.create(
                document=self.document,
                extract=self.extract,
                column=self.column,
                creator=self.user,
                data={
                    "finding": "supported",
                    "rationale": "Deterministic local citation fixture",
                    "evidence": [{"quote": quote, "page": reported}],
                },
            )
            result = self.api(cell)
            (anchor,) = result["findingEvidence"]
            self.assertEqual(
                (anchor["status"], anchor["locatedPage"]), (status, located)
            )
            self.assertEqual(bool(result["fullSourceList"]), located is not None)
            fixtures.append({"name": name, "datacell": result})
        output = os.environ.get("GH8_BROWSER_FIXTURES")
        if output:
            Path(output).write_text(
                json.dumps({"cases": fixtures, "pawls": pawls}, indent=2)
            )

    def test_policy_eligibility_and_shared_passage_associations(self):
        from django.utils import timezone
        from pydantic import BaseModel

        from opencontractserver.annotations.models import (
            TOKEN_LABEL,
            Annotation,
            AnnotationLabel,
            LabelSet,
        )

        class FixtureResponse(BaseModel):
            finding: str
            evidence: list[dict]

        cell = self.cell(["selected words"], None)
        label = AnnotationLabel.objects.create(
            text="Fixture evidence", label_type=TOKEN_LABEL, creator=self.user
        )
        labelset = LabelSet.objects.create(title="Fixture policy", creator=self.user)
        labelset.annotation_labels.add(label)
        binding = {
            "packageHash": "a" * 64,
            "identity": "fixture",
            "owner": "local-fixture",
            "labelIds": {"quote": label.pk},
        }
        self.corpus.label_set = labelset
        self.corpus.workflow_label_policy = binding
        self.corpus.save(update_fields=["label_set", "workflow_label_policy"])
        cell.data_definition = "workflow:" + "a" * 64 + ":quotation"
        cell.completed = timezone.now()
        cell.save(update_fields=["data_definition", "completed"])
        other = Datacell.objects.create(
            document=self.document,
            extract=self.extract,
            column=self.column,
            creator=self.user,
            data=cell.data,
            data_definition=cell.data_definition,
            completed=cell.completed,
        )
        service = "opencontractserver.annotations.services.domain_evidence."
        manifest = {"identity": "fixture", "owner": "local-fixture"}
        policy = {
            "evidence": {
                "by_column": {"quotation": ["quote"]},
                "state_field": "finding",
                "eligible_states": ["supported"],
            }
        }
        with patch(
            service + "resolve_label_policy", return_value=(manifest, policy)
        ), patch(service + "package", return_value=(manifest, None)), patch(
            service + "resolve_response_model", return_value=FixtureResponse
        ):
            (first,) = finding_evidence(cell)
            (second,) = finding_evidence(other)
            self.assertEqual(first["annotationId"], second["annotationId"])
            shared = Annotation.objects.get(pk=first["annotationId"])
            associations = shared.data["domainEvidence"]["associations"]
            self.assertEqual(
                {item["datacellId"] for item in associations}, {cell.pk, other.pk}
            )
            self.assertTrue(all(item["active"] for item in associations))
            cell.corrected_data = {
                "finding": "not_found",
                "evidence": [{"quote": "selected words", "page": None}],
            }
            cell.save(update_fields=["corrected_data"])
            self.assertEqual(finding_evidence(cell), [])
            (historical,) = finding_evidence(cell, "original")
            self.assertEqual(historical["annotationId"], first["annotationId"])
            self.assertEqual(historical["locatedPage"], first["locatedPage"])
            self.assertEqual(list(finding_sources(cell)), [])
            self.assertEqual(finding_evidence(other), [second])
            shared.refresh_from_db()
            self.assertTrue(shared.data["domainEvidence"]["active"])
            active = [
                item
                for item in shared.data["domainEvidence"]["associations"]
                if item["active"]
            ]
            # Raw provenance stays reversible; normal feeds project only the
            # association belonging to the still-positive effective finding.
            self.assertEqual(
                {item["datacellId"] for item in active}, {cell.pk, other.pk}
            )
            from opencontractserver.annotations.services.evidence_visibility import (
                filter_finding_annotations,
            )

            (visible,) = filter_finding_annotations(
                Annotation.objects.filter(pk=shared.pk)
            )
            projected = visible._projected_domain_provenance["associations"]
            self.assertEqual([item["datacellId"] for item in projected], [other.pk])
