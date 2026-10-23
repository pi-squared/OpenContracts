"""Register the preserved native-word PDF route with the stock pipeline."""

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.parsers.native_pdf import parse_native_pdf


class PyMuPDFParser(BaseParser):
    title = "PyMuPDF Native Text"
    description = "Reads native PDF text and token geometry; pages without native text require review."
    author = "OpenContracts"
    dependencies = ["pymupdf"]
    supported_file_types = [FileTypeEnum.PDF]

    def _parse_document_impl(self, user_id, doc_id, **all_kwargs):
        import pymupdf

        document = Document.objects.get(pk=doc_id)
        try:
            with document.pdf_file.open("rb") as source:
                return parse_native_pdf(
                    source.read(),
                    title=document.title,
                    description=document.description or "",
                )
        except (ValueError, pymupdf.FileDataError) as exc:
            raise DocumentParsingError(str(exc), is_transient=False) from exc
