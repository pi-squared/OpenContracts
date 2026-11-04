"""Historical quotation presentation never upgrades an unavailable location."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from opencontractserver.annotations.models import Annotation
from opencontractserver.annotations.services.evidence_visibility import fingerprint
from opencontractserver.extracts.services.quotation_evidence import (
    finding_sources,
    original_projection,
)


class OriginalEvidenceProjectionTests(SimpleTestCase):
    def setUp(self):
        self.value = {
            "finding": "present_blank",
            "evidence": [
                {"quote": "Rate label", "page": 3},
                {"quote": "%", "page": 3},
            ],
        }
        self.cell = SimpleNamespace(
            pk=101,
            document_id=301,
            extract=SimpleNamespace(corpus_id=401),
        )
        self.quotes = [
            {
                "quote": "Rate label",
                "status": "matched",
                "reportedPage": 3,
                "locatedPage": 3,
                "selectionPath": "/evidence/0",
                "annotationId": 501,
            },
            {
                "quote": "%",
                "status": "ambiguous",
                "reportedPage": 3,
                "locatedPage": None,
                "selectionPath": "/evidence/1",
                "annotationId": None,
            },
        ]
        self.matched = self.annotation(601, "/evidence/0", "Rate label")
        self.unrelated = self.annotation(602, "/evidence/1", "Document heading")
        self.annotations = [self.matched, self.unrelated]

    def annotation(
        self, identifier, path, text, cell_id=101, version="original", value=None
    ):
        return SimpleNamespace(
            pk=identifier,
            raw_text=text,
            annotation_label=SimpleNamespace(text="Rate disclosure"),
            data={
                "domainEvidence": {
                    "managed": True,
                    "associations": [
                        {
                            "datacellId": cell_id,
                            "findingVersion": version,
                            "findingFingerprint": fingerprint(value or self.value),
                            "kind": "quote",
                            "selection": {"selectionPath": path},
                        }
                    ],
                }
            },
        )

    def projection(self, quotes=None, value=None, cell=None):
        with patch.object(Annotation.objects, "filter") as query:
            query.return_value.select_related.return_value = self.annotations
            return original_projection(
                cell or self.cell,
                value or self.value,
                self.quotes if quotes is None else quotes,
            )

    def test_ambiguous_original_keeps_quote_without_legacy_selected_source(self):
        before = deepcopy((self.value, self.quotes, self.annotations))
        result = self.projection()
        self.assertEqual([quote["quote"] for quote in result], ["Rate label", "%"])
        self.assertEqual(result[0]["annotationIds"], [601])
        self.assertEqual(result[1]["status"], "ambiguous")
        self.assertIsNone(result[1]["locatedPage"])
        self.assertIsNone(result[1]["annotationId"])
        self.assertEqual(result[1].get("annotationIds", []), [])
        self.assertEqual((self.value, self.quotes, self.annotations), before)

    def test_unlocated_statuses_cannot_reuse_cached_or_retained_annotation_ids(self):
        for status in (
            "ambiguous",
            "unmatched",
            "source_unavailable",
            "projection_unavailable",
        ):
            with self.subTest(status=status):
                quotes = deepcopy(self.quotes)
                quotes[1].update(status=status, annotationId=602, annotationIds=[602])
                before = deepcopy(quotes)
                result = self.projection(quotes=quotes)
                self.assertIsNone(result[1]["annotationId"])
                self.assertEqual(result[1]["annotationIds"], [])
                self.assertEqual(quotes, before)

    def test_matched_and_different_page_originals_keep_located_domain_sources(self):
        for status in ("matched", "different_page"):
            with self.subTest(status=status):
                quotes = deepcopy(self.quotes[:1])
                quotes[0].update(status=status, locatedPage=4)
                result = self.projection(quotes=quotes)
                self.assertEqual(result[0]["annotationId"], 601)
                self.assertEqual(result[0]["annotationIds"], [601])
                self.assertEqual(result[0]["status"], status)
                self.assertEqual(result[0]["locatedPage"], 4)
                self.assertEqual(
                    result[0]["domainLabels"], [{"text": "Rate disclosure"}]
                )

    def test_other_cell_version_or_fingerprint_does_not_supply_original_source(self):
        self.annotations = [
            self.annotation(701, "/evidence/0", "Other finding", cell_id=102),
            self.annotation(702, "/evidence/0", "Corrected value", version="corrected"),
            self.annotation(703, "/evidence/0", "Old value", value={"evidence": []}),
        ]
        result = self.projection()
        self.assertEqual(result[0]["annotationId"], 501)
        self.assertNotIn("annotationIds", result[0])
        # The selected stored matched anchor remains valid when no exact domain
        # association exists; another finding/version never replaces it.
        other = self.projection(
            cell=SimpleNamespace(pk=103, document_id=301, extract=self.cell.extract)
        )
        self.assertEqual(other[0]["annotationId"], 501)

    def test_original_full_source_list_excludes_ambiguous_legacy_domain_source(self):
        projected = self.projection()
        before = deepcopy([annotation.data for annotation in self.annotations])
        with (
            patch(
                "opencontractserver.extracts.services.quotation_evidence.finding_evidence",
                return_value=projected,
            ) as evidence,
            patch.object(Annotation.objects, "filter") as query,
        ):
            query.side_effect = lambda **kwargs: [
                annotation
                for annotation in self.annotations
                if annotation.pk in kwargs["pk__in"]
            ]
            result = finding_sources(self.cell, "original")
            evidence.assert_called_once_with(self.cell, "original")
        self.assertEqual([annotation.pk for annotation in result], [601])
        self.assertEqual([annotation.data for annotation in self.annotations], before)

    def test_effective_source_selection_and_no_evidence_original_remain_separate(self):
        corrected = self.annotation(
            801, "/evidence/0", "Corrected rate", version="corrected"
        )
        with (
            patch(
                "opencontractserver.extracts.services.quotation_evidence.finding_evidence",
                return_value=[{"annotationId": 801}],
            ) as evidence,
            patch.object(
                Annotation.objects, "filter", return_value=[corrected]
            ) as query,
        ):
            self.assertEqual(list(finding_sources(self.cell)), [corrected])
            evidence.assert_called_once_with(self.cell, "effective")
            query.assert_called_once_with(pk__in=[801], document_id=301)
        self.assertEqual(
            self.projection(value={"finding": "not_found", "evidence": []}), []
        )
