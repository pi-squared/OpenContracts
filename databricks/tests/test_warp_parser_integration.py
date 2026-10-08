"""Exercise the real pinned Warp parser export, without model invocations.

Run in an isolated Warp environment with WARP_TEST_SOURCE pointing to the
private, unchanged issue-39 PDF and NLTK_DATA to prefetched English resources.
The ordinary fixture suite skips this configured integration test explicitly.
"""

import hashlib
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402
from unittest.mock import patch  # noqa: E402

parser_source = os.environ.get("WARP_TEST_ASSEMBLED_SOURCE")
sys.path.insert(
    0, parser_source or str(Path(__file__).resolve().parent.parent / "port/python")
)
from databricks_port.warp_pdf import parse_warp_pdf  # noqa: E402


@unittest.skipUnless(os.environ.get("WARP_TEST_SOURCE"), "needs private Warp source")
class WarpParserIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(os.environ["WARP_TEST_SOURCE"])
        content = source.read_bytes()
        if (
            hashlib.sha256(content).hexdigest()
            != "66573a73a38cf99e93623c34778c32f38abe834bec00e5669ac8cff59b50469e"
        ):
            raise ValueError("private regression source differs")
        cls.result = parse_warp_pdf(
            content,
            title="Private issue-39 regression",
            disable_ocr=not bool(os.environ.get("WARP_TEST_AUTO_OCR")),
        )
        cls.export = cls.result.export
        if source.read_bytes() != content:
            raise ValueError("original source changed")

    def test_customer_agreement_passages_stay_in_their_original_column(self):
        export = self.export
        crossing = 0
        tokens = export["pawls_file_content"][3]["tokens"]
        for annotation in export["labelled_text"]:
            if annotation["annotationLabel"] == "Semantic Unit":
                continue
            payload = annotation["annotation_json"].get("3", {})
            selected = [
                tokens[ref["tokenIndex"]] for ref in payload.get("tokensJsons", [])
            ]
            left = any(t["x"] < 276.7 and 20 < t["y"] < 816 for t in selected)
            right = any(t["x"] >= 291 and 20 < t["y"] < 816 for t in selected)
            crossing += int(left and right)
        self.assertEqual(crossing, 0, "fine passages join unrelated agreement panels")

    @unittest.skipUnless(os.environ.get("WARP_TEST_REFERENCE"), "needs stock reference")
    def test_column_regrouping_keeps_every_stock_fine_passage_token_reference(self):
        reference_bytes = Path(os.environ["WARP_TEST_REFERENCE"]).read_bytes()
        self.assertEqual(
            hashlib.sha256(reference_bytes).hexdigest(),
            "85e6e9cdd696cfd27a4e9488f0cf1c57313c9e98a19c6e935af32ff9ba88f109",
        )
        reference = json.loads(reference_bytes)

        def covered(data, index):
            tokens = data["pawls_file_content"][index]["tokens"]
            return {
                hashlib.sha256(
                    json.dumps(
                        [
                            tokens[ref["tokenIndex"]][key]
                            for key in ("text", "x", "y", "width")
                        ]
                    ).encode()
                ).hexdigest()
                for annotation in data["labelled_text"]
                if annotation["annotationLabel"] != "Semantic Unit"
                for location in [annotation["annotation_json"].get(str(index), {})]
                for ref in location.get("tokensJsons", [])
            }

        for index in range(11):
            self.assertEqual(
                covered(reference, index),
                covered(self.export, index),
                f"fine-passage word coverage differs on physical page {index + 1}",
            )

    @unittest.skipUnless(os.environ.get("WARP_TEST_REFERENCE"), "needs stock reference")
    def test_all_native_word_geometry_and_unchanged_pages_retain_stock_evidence(self):
        reference = json.loads(Path(os.environ["WARP_TEST_REFERENCE"]).read_text())
        self.assertEqual(self.export["page_count"], 11)
        self.assertEqual(len(self.export["pawls_file_content"]), 11)
        for index, (candidate, previous) in enumerate(
            zip(self.export["pawls_file_content"], reference["pawls_file_content"])
        ):
            self.assertEqual(candidate["page"], previous["page"])
            self.assertEqual(candidate["page"]["index"], index)

            def words(tokens):
                return Counter(
                    hashlib.sha256(
                        json.dumps(
                            [t[key] for key in ("text", "x", "y", "width")]
                        ).encode()
                    ).hexdigest()
                    for t in tokens
                )

            self.assertEqual(
                words(candidate["tokens"]),
                words(previous["tokens"]),
                f"word geometry differs on physical page {index + 1}",
            )
            if index not in (3, 6):

                def passages(data):
                    return [
                        {
                            key: a[key]
                            for key in ("annotationLabel", "rawText", "annotation_json")
                        }
                        for a in data["labelled_text"]
                        if a["annotationLabel"] != "Semantic Unit"
                        and str(index) in a["annotation_json"]
                    ]

                self.assertEqual(
                    hashlib.sha256(
                        json.dumps(passages(self.export), sort_keys=True).encode()
                    ).hexdigest(),
                    hashlib.sha256(
                        json.dumps(passages(reference), sort_keys=True).encode()
                    ).hexdigest(),
                    f"unchanged passages differ on physical page {index + 1}",
                )

    @unittest.skipUnless(os.environ.get("WARP_TEST_REFERENCE"), "needs stock reference")
    def test_genuine_page_10_fee_table_remains_identical_to_stock(self):
        reference = json.loads(Path(os.environ["WARP_TEST_REFERENCE"]).read_text())
        keys = ("annotationLabel", "rawText", "annotation_json")
        candidate = [
            {key: a[key] for key in keys}
            for a in self.export["labelled_text"]
            if a["page"] == 9 and a["annotationLabel"] != "Semantic Unit"
        ]
        expected = [
            {key: a[key] for key in keys}
            for a in reference["labelled_text"]
            if a["page"] == 9 and a["annotationLabel"] != "Semantic Unit"
        ]
        # Hash comparisons keep contractual text out of failing test output.
        self.assertEqual(
            hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest(),
            hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(),
        )
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    self.export["pawls_file_content"][9], sort_keys=True
                ).encode()
            ).hexdigest(),
            hashlib.sha256(
                json.dumps(reference["pawls_file_content"][9], sort_keys=True).encode()
            ).hexdigest(),
        )


@unittest.skipUnless(
    os.environ.get("WARP_RUNTIME_ROOT"), "needs assembled Warp runtime"
)
class WarpLayoutControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymupdf

        controls = json.loads(
            (Path(__file__).parent / "fixtures/warp-layout-controls.json").read_text()
        )
        cls.controls = {}
        cls.sources = {}
        for name, gold in controls.items():
            with pymupdf.open() as pdf:
                width, height = gold["dimensions"][0]
                page = pdf.new_page(width=width, height=height)
                table = gold.get("table")
                if table:
                    left, top, right, bottom = table["bounds"]
                    page.draw_rect(pymupdf.Rect(left, top, right, bottom))
                    for x in (200, 280):
                        page.draw_line((x, top), (x, bottom))
                    for y in (180, 220):
                        page.draw_line((left, y), (right, y))
                for region in gold["regions"]:
                    remaining = page.insert_textbox(
                        pymupdf.Rect(region["bounds"]), region["text"], fontsize=11
                    )
                    if remaining < 0:
                        raise ValueError(
                            "control text does not fit its independently specified region"
                        )
                source = pdf.tobytes()
            cls.controls[name] = (
                gold,
                parse_warp_pdf(source, title=name, disable_ocr=True),
            )
            cls.sources[name] = source

    def test_genuine_table_rows_exclude_the_independent_side_note(self):
        gold, result = self.controls["genuine-table"]
        fine = [
            a
            for a in result.export["labelled_text"]
            if a["annotationLabel"] != "Semantic Unit"
        ]
        for row in gold["table"]["rows"]:
            passages = [
                a for a in fine if " ".join(row) in " ".join(a["rawText"].split())
            ]
            self.assertTrue(passages, "a genuine table row is missing")
            self.assertTrue(
                all(
                    not any(
                        term in a["rawText"] for term in gold["forbidden_quote_terms"]
                    )
                    for a in passages
                )
            )

    def test_legitimate_quotation_continues_across_columns_without_the_footnote(self):
        gold, result = self.controls["legitimate-column-continuation"]
        fine = [
            a
            for a in result.export["labelled_text"]
            if a["annotationLabel"] != "Semantic Unit"
        ]
        content = " ".join(" ".join(a["rawText"].split()) for a in fine)
        self.assertIn(gold["expected_paragraph"], content)
        self.assertIn(gold["selected_quote"], content)

    def test_source_parser_settings_and_export_define_distinct_parse_identities(self):
        _gold, result = self.controls["genuine-table"]
        provenance = result.provenance
        self.assertEqual(provenance["parser_version"], "2.1.0+oc39.1")
        self.assertTrue(provenance["configuration"]["disable_ocr"])
        self.assertEqual(
            provenance["source_sha256"],
            hashlib.sha256(self.sources["genuine-table"]).hexdigest(),
        )
        other = self.controls["legitimate-column-continuation"][1].provenance
        self.assertEqual(
            provenance["parser_revision_sha256"], other["parser_revision_sha256"]
        )
        self.assertNotEqual(
            provenance["parsing_artifact_sha256"], other["parsing_artifact_sha256"]
        )

    def test_relative_runtime_interpreter_keeps_venv_when_worker_changes_directory(
        self,
    ):
        # Databricks Apps can launch Python as `.venv/bin/python`. The worker
        # changes cwd, so its interpreter must become absolute while retaining
        # the virtual environment path rather than resolving its symlink.
        relative = os.path.relpath(sys.executable, Path.cwd())
        self.assertFalse(Path(relative).is_absolute())
        with patch.object(sys, "executable", relative):
            result = parse_warp_pdf(
                self.sources["genuine-table"],
                title="Relative app interpreter",
                disable_ocr=True,
            )
        self.assertEqual(result.provenance["parser_version"], "2.1.0+oc39.1")
        self.assertEqual(
            result.provenance["source_sha256"],
            hashlib.sha256(self.sources["genuine-table"]).hexdigest(),
        )

    @unittest.skipUnless(
        os.environ.get("WARP_TEST_STAGED_RELEASE"), "needs actual staged launcher"
    )
    def test_actual_staged_launcher_keeps_venv_through_both_directory_changes(self):
        staged = Path(os.environ["WARP_TEST_STAGED_RELEASE"]).resolve()
        with tempfile.TemporaryDirectory(
            prefix="opencontracts-launch-control-"
        ) as temporary:
            initial = Path(temporary)
            (initial / ".venv").symlink_to(Path(sys.prefix), target_is_directory=True)
            source, output = initial / "control.pdf", initial / "result.json"
            source.write_bytes(self.sources["genuine-table"])
            # Execute the actual staged outer launcher and its verified archive.
            # Substitute only the server entrypoint: the real unpacked parser
            # still launches its worker from a second temporary directory.
            code = """
import json, runpy, sys
from pathlib import Path
launcher, source, output = map(Path, sys.argv[1:])
sys.executable = '.venv/bin/python'
def enter(path, run_name):
    assert Path(path) == Path.cwd() / 'app.py'
    from databricks_port.warp_pdf import parse_warp_pdf
    assert Path(parse_warp_pdf.__code__.co_filename).parent.parent == Path.cwd()
    result = parse_warp_pdf(source.read_bytes(), title='Actual launcher control', disable_ocr=True)
    output.write_text(json.dumps({'version': result.provenance['parser_version'],
        'source_sha256': result.provenance['source_sha256'],
        'interpreter': sys.executable, 'runtime': str(Path.cwd())}))
runpy.run_path = enter
exec(compile(launcher.read_text(), str(launcher), 'exec'), {'__file__': str(launcher), '__name__': '__main__'})
"""
            environment = {**os.environ, "PYTHONPATH": ""}
            environment.pop("WARP_RUNTIME_ROOT", None)
            completed = subprocess.run(
                [
                    str(initial / ".venv/bin/python"),
                    "-c",
                    code,
                    str(staged / "app.py"),
                    str(source),
                    str(output),
                ],
                cwd=initial,
                env=environment,
                capture_output=True,
                text=True,
                timeout=600,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(output.read_text())
            self.assertEqual(result["version"], "2.1.0+oc39.1")
            self.assertEqual(
                result["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
            )
            self.assertEqual(result["interpreter"], str(initial / ".venv/bin/python"))
            self.assertTrue(
                Path(result["runtime"]).name.startswith("opencontracts-runtime-")
            )

    def test_raster_page_invokes_the_local_headless_ocr_backend(self):
        import pymupdf

        with pymupdf.open() as original:
            page = original.new_page(width=500, height=180)
            page.insert_text((35, 95), "OCR CONTROL 7342", fontsize=28)
            pixels = page.get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")
        with pymupdf.open() as raster:
            page = raster.new_page(width=500, height=180)
            page.insert_image(page.rect, stream=pixels)
            self.assertEqual(page.get_text(), "")
            source = raster.tobytes()
        result = parse_warp_pdf(source, title="Synthetic raster OCR control")
        text = " ".join(
            t["text"] for p in result.export["pawls_file_content"] for t in p["tokens"]
        )
        self.assertIn("OCR", text)
        self.assertIn("7342", text)
        self.assertEqual(result.provenance["packages"]["onnxruntime"], "1.22.1")
        self.assertEqual(
            result.provenance["packages"]["rapidocr-onnxruntime"], "1.4.4+oc39.1"
        )


if __name__ == "__main__":
    unittest.main()
