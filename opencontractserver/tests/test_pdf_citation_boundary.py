"""Actual retrieval serializers with deterministic documents and projection.

No embedding, repair, assessment or database is needed. Native model instances
retain their zero-based geometry; only document loading/projection is replaced.
Run with Django's test settings:
    python manage.py test opencontractserver.tests.test_pdf_citation_boundary
"""

import copy
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from opencontractserver.annotations.models import Annotation, StructuralAnnotationSet
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools.search import (
    asearch_exact_text_as_sources,
    search_exact_text_as_sources,
)
from opencontractserver.llms.vector_stores.core_vector_stores import VectorSearchResult
from opencontractserver.llms.vector_stores.pydantic_ai_vector_stores import (
    PydanticAIVectorSearchResponse,
)


class PDFCitationBoundaryTests(SimpleTestCase):
    def setUp(self):
        # Public-style three-page document: cover, printed page 1, printed page 2.
        self.document = Document(pk=17, file_type="application/pdf", page_count=3)

    def test_effective_model_tool_descriptions_explain_page_conventions(self):
        from opencontractserver.llms.agents.pydantic_ai_agents import (
            _make_similarity_search_tool,
        )
        from opencontractserver.llms.tools.pydantic_ai_tools import (
            PydanticAIToolWrapper,
        )
        from opencontractserver.llms.tools.tool_factory import create_document_tools
        from opencontractserver.llms.tools.tool_registry import AVAILABLE_TOOLS

        definitions = {tool.name: tool for tool in AVAILABLE_TOOLS}
        for name in ("similarity_search", "search_exact_text"):
            self.assertIn("one-based physical", definitions[name].description)
            self.assertIn("cover", definitions[name].description)
        tools = {tool.name: tool for tool in create_document_tools()}
        exact = PydanticAIToolWrapper(tools["search_exact_text_as_sources"])
        self.assertIn("one-based physical", exact.to_dict()["description"])
        self.assertIn(
            "one-based physical", _make_similarity_search_tool(Mock()).__doc__ or ""
        )
        self.assertIn("one-based physical", tools["get_page_image"].description)
        for name in ("list_document_images", "get_document_image"):
            self.assertIn("zero-based", tools[name].description)
            self.assertIn("citation page", tools[name].description)

    def geometry(self, *indices):
        return {
            str(index): {
                "bounds": {"top": 10, "left": 20, "right": 100, "bottom": 30},
                "tokensJsons": [{"pageIndex": index, "tokenIndex": 0}],
                "rawText": "quotation",
            }
            for index in indices
        }

    def test_real_pawls_projection_keeps_native_tokens_on_first_middle_last_page(self):
        pawls = [
            {
                "page": {"index": index, "width": 612, "height": 792},
                "tokens": [{"text": text, "x": 20, "y": 10, "width": 80, "height": 20}],
            }
            for index, text in enumerate(["Cover", "Middle", "Last"])
        ]
        file = Mock()
        file.open.side_effect = lambda *args: io.StringIO(json.dumps(pawls))
        document = SimpleNamespace(
            file_type="application/pdf", page_count=3, pawls_parse_file=file
        )
        with patch.object(Document.objects, "get", return_value=document):
            sources = search_exact_text_as_sources(17, ["Cover", "Middle", "Last"])
        self.assertEqual([source.metadata["page"] for source in sources], [1, 2, 3])
        for index, source in enumerate(sources):
            payload = source.to_dict()["json"]
            self.assertEqual(list(payload), [index])
            self.assertEqual(
                payload[index]["tokensJsons"], [{"pageIndex": index, "tokenIndex": 0}]
            )
            self.assertEqual(source.metadata["pages"], [index + 1])

    def test_already_one_based_page_image_input_is_not_converted(self):
        from opencontractserver.llms.tools.core_tools.page_images import get_page_image

        file = Mock()
        file.open.side_effect = lambda *args: io.BytesIO(b"fixture PDF")
        document = SimpleNamespace(
            file_type="application/pdf", page_count=3, pdf_file=file
        )
        image = Mock()
        image.save.side_effect = lambda destination, **kwargs: destination.write(
            b"image"
        )
        with (
            patch.object(Document.objects, "get", return_value=document),
            patch("pdf2image.convert_from_bytes", return_value=[image]) as render,
        ):
            for page in (1, 2, 3):
                self.assertEqual(get_page_image(17, page), "aW1hZ2U=")
                self.assertEqual(render.call_args.kwargs["first_page"], page)
                self.assertEqual(render.call_args.kwargs["last_page"], page)
            for invalid in (0, 4):
                with self.assertRaises(ValueError):
                    get_page_image(17, invalid)
            self.assertEqual(render.call_count, 3)

    def test_embedded_image_indices_stay_zero_based(self):
        from opencontractserver.llms.tools.image_tools import list_document_images

        pawls = [{"tokens": [{"is_image": True, "width": 10, "height": 10}]}] * 3
        with (
            patch.object(Document.objects, "get", return_value=self.document),
            patch(
                "opencontractserver.llms.tools.image_tools.load_pawls_data",
                return_value=pawls,
            ),
        ):
            self.assertEqual(
                [image.page_index for image in list_document_images(17)], [0, 1, 2]
            )
            self.assertEqual(
                [image.page_index for image in list_document_images(17, page_index=1)],
                [1],
            )

    def test_non_pdf_exact_search_preserves_offsets_and_existing_page(self):
        document = SimpleNamespace(file_type="text/plain", txt_extract_file=Mock())
        with (
            patch.object(Document.objects, "get", return_value=document),
            patch(
                "opencontractserver.llms.tools.core_tools.search.read_field_file_text",
                return_value="prefix quotation suffix",
            ),
        ):
            (source,) = search_exact_text_as_sources(17, ["quotation"])
        result = source.to_dict()
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["json"], {"start": 7, "end": 16})
        self.assertNotIn("page_convention", result)

    def test_exact_search_and_async_wrapper_convert_once_preserving_geometry(self):
        for index, expected in [
            (0, 1),
            (1, 2),
            (2, 3),
            (None, None),
            (-1, None),
            (3, None),
        ]:
            with self.subTest(index=index):
                geometry = self.geometry(0, 1)
                projected = {"annotation_json": geometry}
                if index is not None:
                    projected["page"] = index
                original = copy.deepcopy(projected)
                layer = Mock(doc_text="quotation")
                layer.create_opencontract_annotation_from_span.return_value = projected
                file = Mock()
                file.open.side_effect = lambda *args: io.StringIO("[]")
                document = SimpleNamespace(
                    file_type="application/pdf", page_count=3, pawls_parse_file=file
                )
                with (
                    patch.object(Document.objects, "get", return_value=document),
                    patch(
                        "plasmapdf.models.PdfDataLayer.build_translation_layer",
                        return_value=layer,
                    ),
                ):
                    for search in (
                        search_exact_text_as_sources,
                        async_to_sync(asearch_exact_text_as_sources),
                    ):
                        (source,) = search(17, ["quotation"], corpus_id=23)
                        result = source.to_dict()
                        self.assertEqual(result["page"], expected)
                        self.assertEqual(result["pages"], [1, 2])
                        self.assertEqual(result["json"], geometry)
                        self.assertEqual(result["document_id"], 17)
                        self.assertEqual(result["corpus_id"], 23)
                        self.assertEqual(
                            (result["char_start"], result["char_end"]), (0, 9)
                        )
                        self.assertIn("cover", result["page_convention"])
                self.assertEqual(projected, original)

    def test_sync_and_async_similarity_contract(self):
        for index, expected in [
            (0, 1),
            (1, 2),
            (2, 3),
            (None, None),
            (-1, None),
            (3, None),
            (True, None),
            (1.5, None),
        ]:
            for compact in (False, True):
                with self.subTest(index=index, compact=compact):
                    geometry = self.geometry(1, 2)
                    if compact:
                        geometry = {
                            "v": 2,
                            "p": {
                                "1": {"b": [10, 20, 100, 30], "t": "0"},
                                "2": {"b": [10, 20, 100, 30], "t": "0"},
                            },
                        }
                    annotation = Annotation(
                        pk=19,
                        document=self.document,
                        raw_text="quotation",
                        json=geometry,
                        corpus_id=23,
                    )
                    # Deliberately exercise malformed/absent legacy page values.
                    setattr(annotation, "page", index)
                    before = copy.deepcopy(annotation.json)
                    hit = VectorSearchResult(
                        annotation=annotation, similarity_score=0.75, block_context=None
                    )
                    for serialize in (
                        PydanticAIVectorSearchResponse.from_core_results,
                        async_to_sync(
                            PydanticAIVectorSearchResponse.async_from_core_results
                        ),
                    ):
                        (result,) = serialize([hit]).results
                        self.assertEqual(result["page"], expected)
                        self.assertEqual(result["pages"], [2, 3])
                        self.assertEqual(result["json"], before)
                        self.assertEqual(result["annotation_id"], 19)
                        self.assertEqual(result["document_id"], 17)
                        self.assertEqual(result["corpus_id"], 23)
                    self.assertEqual(annotation.page, index)
                    self.assertEqual(annotation.json, before)

    def test_non_pdf_similarity_preserves_no_page_sentinel_and_offsets(self):
        self.document.file_type = "text/plain"
        for page in (0, 1, None):
            annotation = Annotation(
                pk=19,
                document=self.document,
                raw_text="quotation",
                json={"start": 14, "end": 23},
            )
            setattr(annotation, "page", page)
            hit = VectorSearchResult(
                annotation=annotation, similarity_score=1, block_context=None
            )
            for serialize in (
                PydanticAIVectorSearchResponse.from_core_results,
                async_to_sync(PydanticAIVectorSearchResponse.async_from_core_results),
            ):
                (result,) = serialize([hit]).results
                self.assertEqual(result["page"], page)
                self.assertEqual(result["json"], {"start": 14, "end": 23})
                self.assertNotIn("page_convention", result)

    def test_unresolved_shared_structural_source_has_no_invented_citation_page(self):
        shared = StructuralAnnotationSet(pk=31, content_hash="fixture-content")
        annotation = Annotation(
            pk=19,
            document=None,
            structural=True,
            structural_set=shared,
            page=0,
            raw_text="quotation",
            json=self.geometry(0),
        )
        original = copy.deepcopy(annotation.json)
        hit = VectorSearchResult(
            annotation=annotation, similarity_score=1, block_context=None
        )
        for serialize in (
            PydanticAIVectorSearchResponse.from_core_results,
            async_to_sync(PydanticAIVectorSearchResponse.async_from_core_results),
        ):
            (result,) = serialize([hit]).results
            self.assertIsNone(result["page"])
            self.assertIsNone(result["document_id"])
            self.assertEqual(result["annotation_id"], 19)
            self.assertEqual(result["json"], original)
        self.assertEqual(annotation.page, 0)
        self.assertEqual(annotation.structural_set_id, 31)
