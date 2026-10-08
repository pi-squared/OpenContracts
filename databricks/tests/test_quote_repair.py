"""Verify text selection against retained tokens, including ambiguous repeats."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
from databricks_port.quote_repair import (  # noqa: E402
    fine_passages,
    ground_quotations,
    rank_passages,
)


def inventory(texts):
    pawls, annotations = [], []
    for page, text in enumerate(texts):
        words = text.split()
        pawls.append(
            {
                "page": {"width": 1000, "height": 1000},
                "tokens": [
                    {"text": word, "x": index * 20, "y": 10, "width": 18, "height": 12}
                    for index, word in enumerate(words)
                ],
            }
        )
        annotations.append(
            {
                "id": page,
                "label": "Paragraph",
                "json": {
                    str(page): {
                        "tokensJsons": [
                            {"pageIndex": page, "tokenIndex": index}
                            for index in range(len(words))
                        ]
                    }
                },
            }
        )
    return fine_passages(annotations, pawls)


class QuoteRepairTests(unittest.TestCase):
    def test_tfidf_preserves_top_five_and_export_order_ties(self):
        passages = inventory(
            ["The lender may charge interest.", "No fee is charged."]
            + ["Other text."] * 6
        )
        ranked = rank_passages(passages, "lender charges interest")
        self.assertEqual(ranked[0]["id"], "0")
        self.assertEqual(len(ranked), 5)
        tied = rank_passages(passages, "unseen")
        self.assertEqual([p["id"] for p in tied], ["0", "1", "2", "3", "4"])

    def test_separate_quotes_keep_exact_source_words_and_physical_pages(self):
        passages = inventory(["The lender may charge interest.", "No fee is charged."])
        result = ground_quotations(
            ["may charge interest.", "No fee is charged."], passages, passages
        )
        self.assertEqual(
            [q["quote"] for q in result], ["may charge interest.", "No fee is charged."]
        )
        self.assertEqual(result[1]["words"][0]["page"], 1)
        self.assertEqual([w["token"] for w in result[0]["words"]], [2, 3, 4])

    def test_highest_ranked_unique_passage_resolves_repeat_without_model_location(self):
        passages = inventory(["No fee is charged.", "No fee is charged."])
        result = ground_quotations(
            ["No fee is charged."], [passages[1], passages[0]], passages
        )
        self.assertEqual(result[0]["words"][0]["page"], 1)

    def test_ambiguous_within_top_passage_and_missing_text_remain_unresolved(self):
        passages = inventory(["No fee. No fee."])
        for quote in ("No fee.", "A fee is charged.", "fe"):
            with self.subTest(quote=quote):
                self.assertEqual(ground_quotations([quote], passages, passages), [])

    def test_missing_excerpt_does_not_publish_a_partial_repair(self):
        passages = inventory(["No fee is charged."])
        self.assertEqual(
            ground_quotations(
                ["No fee is charged.", "Interest is waived."], passages, passages
            ),
            [],
        )

    def test_typography_is_normalized_without_changing_any_words(self):
        passages = inventory(["The consumer’s fee is €40."])
        result = ground_quotations(["The consumer's fee is €40."], passages, passages)
        self.assertEqual(result[0]["quote"], "The consumer’s fee is €40.")
        self.assertEqual(
            ground_quotations(["The consumer’s fee is €50."], passages, passages), []
        )

    def test_semantic_groups_are_excluded_and_bad_geometry_is_rejected(self):
        pawls = [
            {
                "page": {"width": 100, "height": 100},
                "tokens": [
                    {"text": "Words", "x": 95, "y": 1, "width": 10, "height": 10}
                ],
            }
        ]
        annotation = {
            "id": 1,
            "label": "Semantic Unit",
            "json": {"0": {"tokensJsons": [{"tokenIndex": 0}]}},
        }
        self.assertEqual(fine_passages([annotation], pawls), [])
        annotation["label"] = "Paragraph"
        with self.assertRaises(ValueError):
            fine_passages([annotation], pawls)


if __name__ == "__main__":
    unittest.main()
