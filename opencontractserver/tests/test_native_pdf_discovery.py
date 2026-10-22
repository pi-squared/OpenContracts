"""An unavailable native parser must not strand another PDF ingest route."""

import importlib.abc
import io
import sys
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentProcessingStatus,
    PipelineSettings,
)
from opencontractserver.pipeline.thumbnailers.pdf_thumbnailer import (
    PdfThumbnailGenerator,
)
from opencontractserver.tasks import doc_tasks


class MissingPyMuPDF(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pymupdf" or fullname.startswith("pymupdf."):
            raise ModuleNotFoundError("No module named 'pymupdf'", name="pymupdf")
        return None


@contextmanager
def without_native_pdf_dependency():
    """Match the former stock image without leaking import state to other tests."""

    def relevant(name):
        return (
            name == "pymupdf"
            or name.startswith("pymupdf.")
            or name
            in (
                "opencontractserver.pipeline.parsers.native_pdf",
                "opencontractserver.pipeline.parsers.pymupdf_parser",
            )
        )

    original = {
        name: module for name, module in sys.modules.copy().items() if relevant(name)
    }
    for name in original:
        del sys.modules[name]
    finder = MissingPyMuPDF()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        for name in list(sys.modules):
            if relevant(name):
                del sys.modules[name]
        sys.modules.update(original)


class NativePdfDiscoveryIsolationTests(SimpleTestCase):
    def test_missing_native_dependency_does_not_block_thumbnail_and_final_unlock(self):
        document = Document(
            pk=123,
            file_type="application/pdf",
            backend_lock=True,
            processing_status=DocumentProcessingStatus.PROCESSING,
        )
        pipeline_settings = MagicMock()
        pipeline_settings.get_preferred_thumbnailer.return_value = None
        paths = MagicMock()
        paths.select_related.return_value.values.return_value.distinct.return_value = []

        with (
            without_native_pdf_dependency(),
            patch.object(doc_tasks.Document.objects, "get", return_value=document),
            patch.object(document, "save"),
            patch.object(
                PipelineSettings, "get_instance", return_value=pipeline_settings
            ),
            patch(
                "opencontractserver.worker_uploads.run_services.suppress_stage",
                return_value=False,
            ),
            patch.object(
                PdfThumbnailGenerator, "generate_thumbnail", return_value=True
            ) as thumbnail,
            patch.object(DocumentPath.objects, "filter", return_value=paths),
            patch.object(doc_tasks, "_create_document_processed_notifications"),
        ):
            # Keep the real discovery call that formerly aborted the chain.
            # Bypass only Celery's minute-long retry delay for this local test.
            getattr(doc_tasks.extract_thumbnail, "_orig_run")(doc_id=document.pk)
            doc_tasks.set_doc_lock_state.run(locked=False, doc_id=document.pk)

        thumbnail.assert_called_once_with(document.pk)
        self.assertFalse(document.backend_lock)
        self.assertEqual(document.processing_status, DocumentProcessingStatus.COMPLETED)

    def test_selecting_native_parser_still_reports_its_missing_dependency(self):
        with without_native_pdf_dependency():
            from opencontractserver.pipeline.parsers.pymupdf_parser import PyMuPDFParser

            parser = PyMuPDFParser(component_settings={})
            with self.assertRaisesRegex(ModuleNotFoundError, "pymupdf"):
                parser._parse_document_impl(user_id=1, doc_id=123)

    def test_installed_native_parser_reads_pdf_text_and_positioned_tokens(self):
        import pymupdf

        from opencontractserver.pipeline.parsers.pymupdf_parser import PyMuPDFParser

        with pymupdf.open() as pdf:
            page = pdf.new_page()
            page.insert_text((40, 60), "Native parser regression")
            source = pdf.tobytes()
        document = SimpleNamespace(
            title="Tiny native PDF", description="", pdf_file=MagicMock()
        )
        document.pdf_file.open.return_value = io.BytesIO(source)
        with patch.object(Document.objects, "get", return_value=document):
            parsed = PyMuPDFParser(component_settings={})._parse_document_impl(
                user_id=1, doc_id=123
            )

        self.assertEqual(parsed["page_count"], 1)
        self.assertIn("Native parser regression", parsed["content"])
        tokens = parsed["pawls_file_content"][0]["tokens"]
        self.assertEqual(
            [token["text"] for token in tokens], ["Native", "parser", "regression"]
        )
        self.assertTrue(
            all(token["width"] > 0 and token["height"] > 0 for token in tokens)
        )
