"""Comment edits retain grounding only for unchanged or removed selections."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from opencontractserver.extracts.services.review_edits import (
    prepare_review_evidence,
    preserve_review_evidence,
)

EVIDENCE = "opencontractserver.extracts.services.quotation_evidence"


class ReviewEditTests(SimpleTestCase):
    def setUp(self):
        self.body: dict[str, Any] = {
            "finding": "present_blank",
            "rationale": "The price field is blank.",
            "evidence": [
                {"quote": "Total price: ____", "page": 2},
                {"quote": "Schedule of payments", "page": 3},
            ],
        }
        self.cell = SimpleNamespace(
            data={"data": deepcopy(self.body)},
            corrected_data=None,
            evidence_anchors={},
        )
        self.anchors: list[dict[str, Any]] = [
            {"selectionPath": "/evidence/0", "annotationIds": [10], "start": 4},
            {"selectionPath": "/evidence/1", "annotationIds": [20], "start": 90},
        ]
        self.edited: dict[str, Any] = {
            "data": deepcopy(self.body),
            "reviewer_feedback": {"verdict_comment": "Please review."},
        }

    @patch(EVIDENCE + ".finding_evidence")
    def test_comments_retain_independent_copies_of_grounding(self, finding):
        finding.return_value = self.anchors
        prepared = prepare_review_evidence(self.cell, self.edited)
        assert prepared is not None
        self.assertEqual(prepared, self.anchors)
        prepared[0]["annotationIds"].append(99)
        self.assertEqual(self.anchors[0]["annotationIds"], [10])
        self.assertEqual(self.cell.data["data"], self.body)

    @patch(EVIDENCE + ".finding_evidence")
    def test_removal_remaps_the_surviving_selection_path(self, finding):
        finding.return_value = self.anchors
        self.edited["data"]["evidence"].pop(0)
        self.assertEqual(
            prepare_review_evidence(self.cell, self.edited),
            [{**self.anchors[1], "selectionPath": "/evidence/0"}],
        )

    @patch(EVIDENCE + ".finding_evidence")
    def test_one_quote_can_retain_multiple_page_projections(self, finding):
        continuation = {**self.anchors[1], "annotationIds": [21], "start": 120}
        finding.return_value = [*self.anchors, continuation]
        self.edited["data"]["evidence"].pop(0)
        self.assertEqual(
            prepare_review_evidence(self.cell, self.edited),
            [
                {**self.anchors[1], "selectionPath": "/evidence/0"},
                {**continuation, "selectionPath": "/evidence/0"},
            ],
        )

    @patch(EVIDENCE + ".finding_evidence")
    def test_content_changes_and_generic_edits_use_normal_grounding(self, finding):
        self.edited["data"]["rationale"] = "A changed assessment."
        self.assertIsNone(prepare_review_evidence(self.cell, self.edited))
        self.assertIsNone(prepare_review_evidence(self.cell, self.cell.data))
        finding.assert_not_called()

    @patch(EVIDENCE + ".finding_evidence")
    def test_new_or_reordered_quotes_cannot_reuse_geometry(self, finding):
        finding.return_value = self.anchors
        self.edited["data"]["evidence"].reverse()
        self.assertIsNone(prepare_review_evidence(self.cell, self.edited))
        self.edited["data"]["evidence"] = [{"quote": "New words", "page": 2}]
        self.assertIsNone(prepare_review_evidence(self.cell, self.edited))

    @patch(EVIDENCE + ".finding_evidence")
    def test_empty_selection_is_an_explicit_preserved_result(self, finding):
        finding.return_value = self.anchors
        self.edited["data"]["evidence"] = []
        self.assertEqual(prepare_review_evidence(self.cell, self.edited), [])

    @patch(EVIDENCE + ".finding_identity")
    def test_legacy_notes_cannot_recover_from_a_stale_original_cache(self, identity):
        self.cell.corrected_data = {
            "data": {**deepcopy(self.body), "reviewer_feedback": {"old": "note"}}
        }
        self.cell.evidence_anchors = {"original": {"fingerprint": "old-source"}}
        identity.return_value = ("original", {}, {}, "new-source")
        self.assertIsNone(prepare_review_evidence(self.cell, self.edited))

    @patch(EVIDENCE + ".finding_identity")
    def test_cache_uses_the_new_identity_and_retains_original_provenance(
        self, identity
    ):
        original = {"fingerprint": "original", "quotes": []}
        self.cell.evidence_anchors = {"original": original}
        self.cell.save = Mock()
        identity.return_value = ("corrected", {}, {"documentId": 1}, "fresh")
        preserve_review_evidence(self.cell, self.anchors)
        self.assertEqual(self.cell.evidence_anchors["original"], original)
        self.assertEqual(
            self.cell.evidence_anchors["corrected"],
            {
                "fingerprint": "fresh",
                "source": {"documentId": 1},
                "quotes": self.anchors,
            },
        )
        self.cell.save.assert_called_once_with(update_fields=["evidence_anchors"])
