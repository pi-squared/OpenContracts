"""Retain verified quotation geometry across comments and quotation-only removal."""

from copy import copy, deepcopy
from typing import Any


def _body(value):
    value = value.get("data", value) if isinstance(value, dict) else value
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if key != "reviewer_feedback"}
    return value


def _without_evidence(value):
    if isinstance(value, list):
        return [_without_evidence(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_evidence(item)
            for key, item in value.items()
            if key not in {"evidence", "evidence_quote"}
        }
    return value


def _identity(selection):
    return {key: item for key, item in selection.items() if key != "selectionPath"}


def prepare_review_evidence(cell, edited_data) -> list[dict[str, Any]] | None:
    """Only reuse geometry when the response differs by review metadata/removal."""
    from opencontractserver.extracts.services.evidence_text import selected_quotes
    from opencontractserver.extracts.services.quotation_evidence import (
        finding_evidence,
        finding_identity,
    )

    if not isinstance(edited_data, dict) or not isinstance(
        edited_data.get("reviewer_feedback"), dict
    ):
        return None
    previous = cell.corrected_data if cell.corrected_data is not None else cell.data
    old_body, new_body = _body(previous), _body(edited_data)
    if not isinstance(old_body, dict) or not isinstance(new_body, dict):
        return None
    if _without_evidence(old_body) != _without_evidence(new_body):
        return None

    old_selections = selected_quotes(old_body)
    new_selections = selected_quotes(new_body)
    # Recover early frontend notes that were embedded in the governed response.
    if isinstance(previous, dict) and isinstance(
        previous.get("data", previous).get("reviewer_feedback"), dict
    ):
        from opencontractserver.extracts.services.quotation_grounding import (
            project_repairs,
        )

        original = (cell.evidence_anchors or {}).get("original", {})
        original_fingerprint = finding_identity(cell, "original")[3]
        if original.get("fingerprint") != original_fingerprint or _without_evidence(
            _body(cell.data)
        ) != _without_evidence(new_body):
            return None
        proxy = copy(cell)
        proxy.corrected_data = None
        grounded = project_repairs(
            proxy, original, deepcopy(original.get("quotes", []))
        )
        old_selections = selected_quotes(cell.data)
    else:
        grounded = finding_evidence(cell)

    by_path: dict[str, list[dict[str, Any]]] = {}
    for item in grounded:
        by_path.setdefault(item["selectionPath"], []).append(item)
    result: list[dict[str, Any]] = []
    cursor = 0
    for selection in new_selections:
        while cursor < len(old_selections) and _identity(
            old_selections[cursor]
        ) != _identity(selection):
            cursor += 1
        if cursor == len(old_selections):
            return None
        previous_selection = old_selections[cursor]
        cursor += 1
        anchors = by_path.get(previous_selection["selectionPath"])
        if anchors is None:
            return None
        result.extend(
            {**deepcopy(anchor), "selectionPath": selection["selectionPath"]}
            for anchor in anchors
        )
    return result


def preserve_review_evidence(cell, quotes: list[dict[str, Any]]) -> None:
    from opencontractserver.extracts.services.quotation_evidence import finding_identity

    version, _, source, fingerprint = finding_identity(cell)
    cache = dict(cell.evidence_anchors or {})
    cache[version] = {"fingerprint": fingerprint, "source": source, "quotes": quotes}
    cell.evidence_anchors = cache
    cell.save(update_fields=["evidence_anchors"])
