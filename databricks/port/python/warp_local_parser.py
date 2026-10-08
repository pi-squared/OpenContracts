"""Register the maintained patched Warp route with native parser persistence."""

from dataclasses import dataclass, field

from databricks_port.warp_pdf import VERSION, parse_warp_pdf

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.utils.structural_sets import create_structural_annotation_set


class WarpLocalParser(BaseParser):
    title = "Warp-Ingest Local"
    description = (
        "Parses original PDF words and tables with the maintained column patch."
    )
    author = "OpenContracts Databricks port"
    dependencies = ["warp-ingest", "nltk", "pymupdf"]
    supported_file_types = [FileTypeEnum.PDF]

    @dataclass
    class Settings:
        apply_ocr: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Force local OCR on every page",
                )
            },
        )
        disable_ocr: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Disable local OCR; mutually exclusive with apply_ocr",
                )
            },
        )
        semantic_units: bool = field(
            default=True,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Append semantic clause annotations",
                )
            },
        )
        include_images: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Include extracted images in the parser export",
                )
            },
        )

    def _parse_document_impl(self, user_id, doc_id, **all_kwargs):
        document = Document.objects.get(pk=doc_id)
        if document.structural_annotation_set_id:
            raise DocumentParsingError(
                "Warp needs a fresh source version; retained parses and their evidence must stay intact",
                is_transient=False,
            )
        try:
            with document.pdf_file.open("rb") as source:
                result = parse_warp_pdf(
                    source.read(),
                    title=document.title,
                    description=document.description or "",
                    **{
                        name: all_kwargs[name]
                        for name in (
                            "apply_ocr",
                            "disable_ocr",
                            "semantic_units",
                            "include_images",
                        )
                        if name in all_kwargs
                    },
                )
        except ValueError as error:
            raise DocumentParsingError(str(error), is_transient=False) from error
        metadata = {**(document.custom_meta or {}), **result.provenance}
        document.custom_meta = metadata
        document.save(update_fields=["custom_meta"])
        return result.export

    def _create_structural_annotation_set(self, document, user):
        metadata = document.custom_meta or {}
        create_structural_annotation_set(
            document,
            user,
            parser_name=self.title,
            parser_version=VERSION,
            artifact_identity=metadata["parsing_artifact_sha256"],
        )
