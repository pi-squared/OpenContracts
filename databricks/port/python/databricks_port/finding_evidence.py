"""Compatibility imports for the native application service boundary."""

from opencontractserver.extracts.services.quotation_evidence import (
    finding_evidence,
    finding_identity,
    finding_sources,
    finish_projection,
    ground_extraction_to_annotations,
    quotation_metadata,
)

__all__ = [
    "finding_identity",
    "quotation_metadata",
    "finish_projection",
    "finding_evidence",
    "finding_sources",
    "ground_extraction_to_annotations",
]
