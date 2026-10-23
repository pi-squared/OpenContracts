"""Persist and expose finding-specific quotation anchors, retaining retrieval history."""

import hashlib
import json
import logging
from typing import Any

from asgiref.sync import sync_to_async

from opencontractserver.extracts.services.evidence_text import (
    finding_outcome,
    locate_finding_evidence,
    normalized_text,
    selected_quotes,
)

logger = logging.getLogger(__name__)


def finding_identity(cell, requested_version="effective"):
    document = cell.document
    if requested_version not in {"effective", "original"}:
        raise ValueError("Unknown finding version")
    version = (
        "corrected"
        if requested_version == "effective" and cell.corrected_data is not None
        else "original"
    )
    value = cell.corrected_data if version == "corrected" else cell.data
    source = {
        "documentId": document.pk,
        "sourceHash": document.pdf_file_hash,
        "structuralSetId": document.structural_annotation_set_id,
        "pawlsFile": document.pawls_parse_file.name,
        "textFile": document.txt_extract_file.name,
    }
    fingerprint = hashlib.sha256(
        json.dumps({"value": value, "source": source}, sort_keys=True).encode()
    ).hexdigest()
    return version, value, source, fingerprint


def quotation_metadata(cell):
    return {
        "quotationEvidence": {"datacellId": cell.pk, "active": True},
        "domainEvidence": {"active": True},
    }


def finish_projection(cell, saved, quotes):
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.annotations.services.evidence_visibility import (
        apply_finding_labels,
    )
    from opencontractserver.extracts.services.quotation_grounding import project_repairs

    value = cell.corrected_data if cell.corrected_data is not None else cell.data
    # Cache entries and repairs are retained provenance, not authority to select
    # evidence. Filter by this version's selections both before and after repairs.
    paths = {item["selectionPath"] for item in selected_quotes(value)}
    quotes = [quote for quote in quotes if quote.get("selectionPath") in paths]
    quotes = project_repairs(cell, saved, quotes) if quotes else []
    quotes = [quote for quote in quotes if quote.get("selectionPath") in paths]
    quotes = apply_finding_labels(cell, quotes)
    active = {
        identifier
        for quote in quotes
        for identifier in quote.get("annotationIds", [quote.get("annotationId")])
        if identifier is not None
    }
    # These rows belong to one finding. Keep the historical M2M links, while
    # ordinary annotation reads display only the current finding's evidence.
    for annotation in Annotation.objects.filter(
        document_id=cell.document_id,
        corpus_id=cell.extract.corpus_id,
        creator_id=cell.creator_id,
        data__quotationEvidence__datacellId=cell.pk,
    ):
        visible = annotation.pk in active
        metadata = dict(annotation.data or {})
        quotation = dict(metadata.get("quotationEvidence", {}))
        domain = dict(metadata.get("domainEvidence", {}))
        if quotation.get("active") != visible or domain.get("active") != visible:
            quotation["active"] = domain["active"] = visible
            metadata.update(quotationEvidence=quotation, domainEvidence=domain)
            annotation.data = metadata
            annotation.save(update_fields=["data"])
    return quotes


def finding_evidence(datacell, version="effective"):
    from django.db import transaction

    from opencontractserver.annotations.compact_json import compact_annotation_json
    from opencontractserver.annotations.models import TOKEN_LABEL, Annotation
    from opencontractserver.annotations.services.evidence_visibility import (
        ensure_selected_policy,
    )
    from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL
    from opencontractserver.extracts.models import Datacell
    from opencontractserver.utils.span_projection import (
        load_document_text_and_layer,
        project_span_to_token_annotation,
    )

    with transaction.atomic():
        cell = (
            Datacell.objects.select_for_update(of=("self",))
            .select_related("document", "extract__corpus")
            .get(pk=datacell.pk)
        )
        document = cell.document
        historical = version == "original"
        cache_version, value, source, fingerprint = finding_identity(cell, version)
        # Universal policy precedes workflow loading and all cached anchors.
        # Do not rewrite retained caches or require a package rebind to hide them.
        if finding_outcome(value) == "not_found":
            return []
        if not historical:
            ensure_selected_policy(cell)
        cache = dict(cell.evidence_anchors or {})
        saved = cache.get(cache_version, {})
        # Source access and annotation writes can recover without a change to
        # the finding or source identity. Retry these unavailable locations.
        if saved.get("fingerprint") == fingerprint and not any(
            quote["status"] in {"source_unavailable", "projection_unavailable"}
            for quote in saved.get("quotes", [])
        ):
            if historical:
                return original_projection(cell, value, saved["quotes"])
            return finish_projection(cell, saved, saved["quotes"])
        selections = selected_quotes(value)
        extract = cell.extract
        corpus = extract.corpus if extract is not None else None
        quotes = []
        if selections:
            try:
                text, layer, annotation_type = load_document_text_and_layer(document)
                if annotation_type != TOKEN_LABEL or layer is None:
                    raise ValueError("Original PDF token coordinates are unavailable")
                page_spans = list(layer.page_dataframe.itertuples(index=False))
                pages = [text[int(page.Start) : int(page.End)] for page in page_spans]
                quotes = locate_finding_evidence(value, pages)
                if corpus is None:
                    raise ValueError("Finding has no retained corpus association")
            except Exception:
                logger.warning(
                    "Finding source is unavailable for cell %s", cell.pk, exc_info=True
                )
                quotes = [
                    {
                        **selection,
                        "status": "source_unavailable",
                        "locatedPage": None,
                        "matchType": None,
                        "annotationId": None,
                    }
                    for selection in selections
                ]
            else:
                label = None
                for quote in quotes:
                    if quote["status"] not in ("matched", "different_page"):
                        continue
                    try:
                        with transaction.atomic():
                            if label is None:
                                from opencontractserver.annotations.models import (
                                    AnnotationLabel,
                                )

                                label_text = (
                                    OC_EXTRACT_SOURCE_LABEL
                                    if corpus.workflow_label_policy and not historical
                                    else "Quotation evidence"
                                )
                                label, _ = AnnotationLabel.objects.get_or_create(
                                    text=label_text,
                                    creator_id=cell.creator_id,
                                    label_type=TOKEN_LABEL,
                                    defaults={"color": "#64748b"},
                                )
                            page_start = int(page_spans[quote["locatedPage"] - 1].Start)
                            payload, page, raw_text = project_span_to_token_annotation(
                                layer,
                                start=page_start + quote["start"],
                                end=page_start + quote["end"],
                                text=quote["quote"],
                                label_text=label.text,
                            )
                            if (
                                normalized_text(raw_text)[0]
                                != normalized_text(quote["quote"])[0]
                            ):
                                raise ValueError(
                                    "Token projection did not retain the complete quotation"
                                )
                            if page != quote["locatedPage"] - 1:
                                raise ValueError(
                                    "Token projection changed physical page"
                                )
                            compacted_payload = compact_annotation_json(payload)
                            if compacted_payload is None:
                                raise ValueError(
                                    "Quotation projection has no coordinates"
                                )
                            payload = compacted_payload
                            ownership: dict[str, Any] = (
                                {}
                                if corpus.workflow_label_policy and not historical
                                else {"data__quotationEvidence__datacellId": cell.pk}
                            )
                            if historical:
                                ownership["data__quotationEvidence__findingVersion"] = (
                                    "original"
                                )
                            defaults: dict[str, Any] = {"json": payload}
                            if ownership:
                                defaults["data"] = quotation_metadata(cell)
                                if historical:
                                    defaults["data"]["quotationEvidence"].update(
                                        active=False, findingVersion="original"
                                    )
                                    defaults["data"]["domainEvidence"]["active"] = False
                            annotation, _ = Annotation.objects.get_or_create(
                                document=document,
                                corpus=corpus,
                                annotation_label=label,
                                annotation_type=TOKEN_LABEL,
                                page=page,
                                raw_text=raw_text,
                                creator_id=cell.creator_id,
                                is_grounding_source=bool(corpus.workflow_label_policy),
                                structural=False,
                                defaults=defaults,
                                **ownership,
                            )
                            if compact_annotation_json(annotation.json) != payload:
                                raise ValueError(
                                    "Existing quotation coordinates differ from the complete selected span"
                                )
                            if not historical:
                                cell.sources.add(annotation)
                            quote["annotationId"] = annotation.pk
                    except Exception:
                        label = None
                        logger.warning(
                            "Complete quotation projection failed for cell %s",
                            cell.pk,
                            exc_info=True,
                        )
                        quote.update(status="projection_unavailable", annotationId=None)
        cache[cache_version] = {
            "fingerprint": fingerprint,
            "source": source,
            "quotes": quotes,
        }
        cell.evidence_anchors = cache
        cell.save(update_fields=["evidence_anchors"])
        datacell.evidence_anchors = cache
        if historical:
            return original_projection(cell, value, quotes)
        return finish_projection(cell, cache[cache_version], quotes)


def original_projection(cell, value, quotes):
    """Read historical labels without activating or reconciling associations."""
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.annotations.services.evidence_visibility import fingerprint

    paths = {item["selectionPath"] for item in selected_quotes(value)}
    raw = value.get("data", value) if isinstance(value, dict) else value
    labels: dict[str | None, list[Annotation]] = {}
    for annotation in Annotation.objects.filter(
        document_id=cell.document_id,
        corpus_id=cell.extract.corpus_id,
        data__domainEvidence__managed=True,
    ).select_related("annotation_label"):
        for item in annotation.data["domainEvidence"].get("associations", []):
            if (
                item.get("datacellId") == cell.pk
                and item.get("findingVersion") == "original"
                and item.get("findingFingerprint") == fingerprint(raw)
                and item.get("kind") == "quote"
            ):
                selection = item.get("selection") or {}
                labels.setdefault(selection.get("selectionPath"), []).append(annotation)
    result = []
    for quote in quotes:
        path = quote.get("selectionPath")
        if path not in paths:
            continue
        annotations = labels.get(path, [])
        if annotations:
            domain_labels = []
            for annotation in annotations:
                label = annotation.annotation_label
                if label is None:
                    raise ValueError("Retained finding annotation has no domain label")
                domain_labels.append({"text": label.text})
            quote = {
                **quote,
                "annotationId": annotations[0].pk,
                "annotationIds": [annotation.pk for annotation in annotations],
                "domainLabels": domain_labels,
            }
        result.append(quote)
    return result


def finding_sources(datacell, version="effective"):
    from opencontractserver.annotations.models import Annotation

    identifiers = [
        identifier
        for quote in finding_evidence(datacell, version)
        for identifier in quote.get("annotationIds", [quote.get("annotationId")])
        if identifier is not None
    ]
    annotations = Annotation.objects.filter(
        pk__in=identifiers, document_id=datacell.document_id
    )
    if version == "original":
        from copy import copy

        from opencontractserver.constants.annotations import OC_EXTRACT_SOURCE_LABEL

        annotations = list(annotations)
        for annotation in annotations:
            annotation._explicit_evidence_quote = True
            # A cached original may reference a hidden retrieval anchor rather
            # than a historical policy label. Present it as selected evidence
            # only in this explicit context, without relabelling the saved row.
            if annotation.annotation_label.text == OC_EXTRACT_SOURCE_LABEL:
                label = copy(annotation.annotation_label)
                label.text = "Quotation evidence"
                annotation.annotation_label = label
    return annotations


async def ground_extraction_to_annotations(
    datacell, document, corpus, user_id, **kwargs
):
    return await sync_to_async(lambda: list(finding_sources(datacell)))()
