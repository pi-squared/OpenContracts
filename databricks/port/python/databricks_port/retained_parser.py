"""Import independently retained parsing artifacts through the stock parser seam."""

import re

from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.utils.structural_sets import create_structural_annotation_set


class RetainedParser(BaseParser):
    def _parse_document_impl(self, *args, **kwargs):
        raise NotImplementedError(
            "Supply verified retained parser data to save_parsed_data"
        )

    def _create_structural_annotation_set(self, document, user):
        metadata = document.custom_meta or {}
        identity = metadata.get("parsing_artifact_sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError(
                "Retained parser import needs a verified artifact identity"
            )
        create_structural_annotation_set(
            document,
            user,
            parser_name=metadata["parser"],
            parser_version=metadata["parser_version"],
            artifact_identity=identity,
        )
