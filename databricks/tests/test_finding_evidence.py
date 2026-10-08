import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
from databricks_port.evidence import locate_finding_evidence  # noqa: E402


class FindingEvidenceTests(unittest.TestCase):
    def test_only_selected_quotes_are_located_and_whole_passages_are_preserved(self):
        finding = {
            "data": {
                "state": "supported",
                "applicability": "consumer",
                "note": "support e",
                "evidence": [
                    {"quote": "The provider's first reply.", "page": 1},
                    {"quote": "The consumer requested accessible letters.", "page": 2},
                    {"quote": "Support was provided after notice.", "page": 3},
                ],
            }
        }
        pages = [
            "consumer supported support e. The provider’s first\nreply.",
            "The consumer requested accessible letters.",
            "Support was provided after notice.",
        ]
        anchors = locate_finding_evidence(finding, pages)
        self.assertEqual(len(anchors), 3)
        self.assertEqual([a["status"] for a in anchors], ["matched"] * 3)
        self.assertEqual([a["locatedPage"] for a in anchors], [1, 2, 3])
        self.assertEqual(anchors[0]["quote"], "The provider's first reply.")
        self.assertEqual(
            pages[0][anchors[0]["start"] : anchors[0]["end"]],
            "The provider’s first\nreply.",
        )

    def test_metadata_and_empty_evidence_do_not_create_annotations(self):
        self.assertEqual(
            locate_finding_evidence(
                {
                    "state": "supported",
                    "applicability": "consumer",
                    "rationale": "The payment was made.",
                    "evidence": [],
                },
                ["consumer supported The payment was made."],
            ),
            [],
        )

    def test_serialized_and_scoped_quotations_keep_attribution(self):
        finding = {
            "evidence_quote": '[{"quote":"The payment was made.","page":1}]',
            "scoped_entries": [
                {
                    "consumer": "consumer 2",
                    "period": "after notice",
                    "value": "support",
                    "evidence": [
                        {
                            "quote": "Accessible support was requested.",
                            "page": 2,
                            "speaker": "consumer",
                        }
                    ],
                }
            ],
        }
        anchors = locate_finding_evidence(
            finding, ["The payment was made.", "Accessible support was requested."]
        )
        self.assertEqual(len(anchors), 2)
        self.assertEqual(
            anchors[1]["scope"], {"consumer": "consumer 2", "period": "after notice"}
        )
        self.assertEqual(anchors[1]["speaker"], "consumer")

    def test_wrong_pages_ambiguity_and_paraphrases_remain_visible(self):
        finding = {
            "evidence": [
                {"quote": "The payment was made.", "page": 9},
                {"quote": "Repeated statement.", "page": 9},
                {"quote": "A different payment was made.", "page": 1},
            ]
        }
        anchors = locate_finding_evidence(
            finding,
            ["The payment was made. Repeated statement.", "Repeated statement."],
        )
        self.assertEqual(
            [a["status"] for a in anchors], ["different_page", "ambiguous", "unmatched"]
        )
        self.assertEqual(anchors[0]["reportedPage"], 9)
        self.assertEqual(anchors[0]["locatedPage"], 1)
        self.assertIsNone(anchors[1]["locatedPage"])
        self.assertIsNone(anchors[2]["locatedPage"])

    def test_declared_page_can_disambiguate_an_identical_quote(self):
        anchors = locate_finding_evidence(
            {"evidence": [{"quote": "Repeated statement.", "page": 2}]},
            ["Repeated statement.", "Repeated statement."],
        )
        self.assertEqual(anchors[0]["locatedPage"], 2)
        self.assertEqual(anchors[0]["status"], "matched")

    def test_substrings_inside_changed_words_are_not_quote_matches(self):
        anchors = locate_finding_evidence(
            {"evidence": [{"quote": "supported", "page": 1}]}, ["unsupported"]
        )
        self.assertEqual(anchors[0]["status"], "unmatched")


if __name__ == "__main__":
    unittest.main()
