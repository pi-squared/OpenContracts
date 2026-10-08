"""Validate PDF evidence at the retained parser export boundary."""

import copy
import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
from databricks_port.parser_exports import warp_export  # noqa: E402


class SourceGeometryTests(unittest.TestCase):
    def fixture(self, *, rotation=0, crop=False, duplicate=False):
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=300, height=300)
            page.insert_text((100, 120), "£", fontname="tiro", fontsize=12)
            if duplicate:
                page.insert_text((102, 122), "£", fontname="tiro", fontsize=12)
            for xref in page.get_contents():
                pdf.update_stream(xref, pdf.xref_stream(xref).replace(b"<a3>", b"<80>"))
            if crop:
                page.set_cropbox(pymupdf.Rect(40, 40, 260, 260))
            page.set_rotation(rotation)
            char = page.get_text("rawdict")["blocks"][0]["lines"][0]["spans"][0][
                "chars"
            ][0]
            box = pymupdf.Rect(char["bbox"]) * page.rotation_matrix
            source = pdf.tobytes()
            dimensions = [(page.rect.width, page.rect.height)]
        token = {
            "text": "€",
            "x": box.x0 + (3 if duplicate else 0),
            "y": box.y0,
            "width": 0,
            "height": box.height,
        }
        raw = {
            "result": {
                "page_count": 1,
                "content": "€",
                "pawls_file_content": [
                    {
                        "page": {
                            "index": 0,
                            "width": dimensions[0][0],
                            "height": dimensions[0][1],
                        },
                        "tokens": [token],
                    }
                ],
                "labelled_text": [
                    {
                        "page": 0,
                        "annotation_json": {
                            "0": {
                                "bounds": {
                                    "left": box.x0,
                                    "top": box.y0,
                                    "right": box.x0,
                                    "bottom": box.y1,
                                },
                                "tokensJsons": [{"pageIndex": 0, "tokenIndex": 0}],
                            }
                        },
                    }
                ],
            }
        }
        return source, dimensions, raw, box

    def test_zero_advance_currency_keeps_text_and_reference_with_source_rectangle(self):
        source, dimensions, raw, box = self.fixture()
        original = copy.deepcopy(raw)
        export = warp_export(raw, dimensions, "Currency", source=source)
        token = export["pawls_file_content"][0]["tokens"][0]
        self.assertEqual(export["content"], "€")
        self.assertAlmostEqual(token["width"], box.width, places=4)
        location = export["labelled_text"][0]["annotation_json"]["0"]
        self.assertEqual(location["tokensJsons"], [{"pageIndex": 0, "tokenIndex": 0}])
        self.assertAlmostEqual(location["bounds"]["right"], box.x1, places=4)
        self.assertEqual(raw, original)

    def test_crop_and_rotation_use_displayed_page_coordinates(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                source, dims, raw, box = self.fixture(rotation=rotation, crop=True)
                export = warp_export(raw, dims, "Rotated", source=source)
                token = export["pawls_file_content"][0]["tokens"][0]
                self.assertAlmostEqual(token["x"], box.x0, places=4)
                self.assertAlmostEqual(token["width"], box.width, places=4)

    def test_ambiguous_glyphs_fail_without_guessing_or_exposing_source_text(self):
        source, dims, raw, _ = self.fixture(duplicate=True)
        with self.assertRaisesRegex(ValueError, "PDF page 1 is ambiguous"):
            warp_export(raw, dims, "Ambiguous", source=source)

    def test_missing_glyph_and_out_of_page_geometry_fail(self):
        source, dims, raw, _ = self.fixture()
        raw["result"]["pawls_file_content"][0]["tokens"][0][
            "text"
        ] = "missing private text"
        with self.assertRaisesRegex(ValueError, "PDF page 1 is unavailable"):
            warp_export(raw, dims, "Missing", source=source)
        raw["result"]["pawls_file_content"][0]["tokens"][0].update(width=5, x=-1)
        with self.assertRaisesRegex(ValueError, "outside the original PDF page"):
            warp_export(raw, dims, "Outside", source=source)


@unittest.skipUnless(
    os.environ.get("WARP_CURRENCY_SOURCE"), "Original public currency PDF required"
)
class CurrencyPdfIntegrationTests(unittest.TestCase):
    def test_original_pdf_parses_all_pages_without_changing_text_or_token_indexes(self):
        from databricks_port.warp_pdf import parse_warp_pdf

        source = Path(os.environ["WARP_CURRENCY_SOURCE"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            "32b4b08f8ce0d22c1fb0448132be82d3306835c04f6f867e54ab55d854b85cad",
        )
        export = parse_warp_pdf(source, title="Currency PDF regression").export
        self.assertEqual(export["page_count"], 8)
        self.assertEqual(len(export["content"]), 31851)
        self.assertEqual(
            sum(len(p["tokens"]) for p in export["pawls_file_content"]), 5854
        )
        self.assertEqual(export["geometry_recovery"]["recovered_tokens"], 18)
        if os.environ.get("WARP_CURRENCY_REFERENCE"):
            previous = json.loads(
                Path(os.environ["WARP_CURRENCY_REFERENCE"]).read_text()
            )["raw"]["result"]
            self.assertEqual(
                hashlib.sha256(export["content"].encode()).digest(),
                hashlib.sha256(previous["content"].encode()).digest(),
            )
            self.assertEqual(
                [
                    [t["text"] for t in p["tokens"]]
                    for p in export["pawls_file_content"]
                ],
                [
                    [t["text"] for t in p["tokens"]]
                    for p in previous["pawls_file_content"]
                ],
            )
            self.assertEqual(
                [
                    [location["tokensJsons"] for location in a["annotation_json"].values()]
                    for a in export["labelled_text"]
                ],
                [
                    [location["tokensJsons"] for location in a["annotation_json"].values()]
                    for a in previous["labelled_text"]
                ],
            )


if __name__ == "__main__":
    unittest.main()
