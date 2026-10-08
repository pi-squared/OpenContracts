"""Persist and expose finding-specific quotation anchors, retaining retrieval history."""

import hashlib
import json
import logging

from asgiref.sync import sync_to_async
from databricks_port.evidence import (
    locate_finding_evidence,
    normalized_text,
    selected_quotes,
)

logger = logging.getLogger(__name__)


def finding_identity(cell):
    document = cell.document
    version = "corrected" if cell.corrected_data is not None else "original"
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
    from databricks_port.domain_labels import apply_finding_labels
    from databricks_port.grounding import project_repairs

    from opencontractserver.annotations.models import Annotation

    quotes = apply_finding_labels(cell, project_repairs(cell, saved, quotes))
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


def finding_evidence(datacell):
    from databricks_port.domain_labels import (
        ensure_selected_policy,
    )
    from django.db import transaction

    from opencontractserver.annotations.compact_json import compact_annotation_json
    from opencontractserver.annotations.models import TOKEN_LABEL, Annotation
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
        ensure_selected_policy(cell)
        document = cell.document
        version, value, source, fingerprint = finding_identity(cell)
        cache = dict(cell.evidence_anchors or {})
        saved = cache.get(version, {})
        # Source access and annotation writes can recover without a change to
        # the finding or source identity. Retry these unavailable locations.
        if saved.get("fingerprint") == fingerprint and not any(
            quote["status"] in {"source_unavailable", "projection_unavailable"}
            for quote in saved.get("quotes", [])
        ):
            return finish_projection(cell, saved, saved["quotes"])
        selections = selected_quotes(value)
        corpus = cell.extract.corpus if cell.extract_id else None
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
                                    if corpus.workflow_label_policy
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
                            payload = compact_annotation_json(payload)
                            ownership = (
                                {}
                                if corpus.workflow_label_policy
                                else {"data__quotationEvidence__datacellId": cell.pk}
                            )
                            defaults = {"json": payload}
                            if ownership:
                                defaults["data"] = quotation_metadata(cell)
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
        cache[version] = {
            "fingerprint": fingerprint,
            "source": source,
            "quotes": quotes,
        }
        cell.evidence_anchors = cache
        cell.save(update_fields=["evidence_anchors"])
        datacell.evidence_anchors = cache
        return finish_projection(cell, cache[version], quotes)


def finding_sources(datacell):
    from opencontractserver.annotations.models import Annotation

    identifiers = [
        identifier
        for quote in finding_evidence(datacell)
        for identifier in quote.get("annotationIds", [quote.get("annotationId")])
        if identifier is not None
    ]
    return Annotation.objects.filter(
        pk__in=identifiers, document_id=datacell.document_id
    )


async def ground_extraction_to_annotations(
    datacell, document, corpus, user_id, **kwargs
):
    return await sync_to_async(lambda: list(finding_sources(datacell)))()
