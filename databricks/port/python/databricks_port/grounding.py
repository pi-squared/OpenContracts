"""Compatibility imports for the native application service boundary."""

from opencontractserver.extracts.services.quotation_grounding import (
    ground_machine_extraction,
    invoke,
    project_repairs,
    quotations_from_response,
    repair_machine_finding,
    request_for,
    source_inventory,
)

__all__ = [
    "source_inventory",
    "request_for",
    "invoke",
    "quotations_from_response",
    "repair_machine_finding",
    "project_repairs",
    "ground_machine_extraction",
]
