"""One durable quotation repair at the machine extraction boundary.

Requests and provider envelopes stay in the application database. Reads and reviewer edits only
project saved evidence. An interrupted invocation is never automatically repeated.
"""

import hashlib
import json
import logging
import os

from opencontractserver.extracts.services.quote_repair import (
    INSTRUCTIONS,
    fine_passages,
    ground_quotations,
    rank_passages,
)

logger = logging.getLogger(__name__)


def source_inventory(document):
    from opencontractserver.annotations.compact_json import iter_page_annotations
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.utils.compact_pawls import expand_pawls_pages

    if document.structural_annotation_set_id is None:
        raise ValueError("Document has no retained structural annotation set")
    with document.pawls_parse_file.open("r") as stream:
        pawls = expand_pawls_pages(json.load(stream))
    annotations = (
        Annotation.objects.filter(
            structural_set_id=document.structural_annotation_set_id,
            structural=True,
        )
        .select_related("annotation_label")
        .order_by("pk")
    )
    records = []
    for annotation in annotations:
        pages = {
            str(page.page_index): {
                "tokensJsons": [
                    {"pageIndex": page.page_index, "tokenIndex": index}
                    for index in page.token_indices
                ]
            }
            for page in iter_page_annotations(
                annotation.json, raw_text=annotation.raw_text
            )
        }
        records.append(
            {
                "id": annotation.pk,
                "label": annotation.annotation_label.text,
                "json": pages,
            }
        )
    return fine_passages(records, pawls)


def request_for(quotation, field, ranked):
    return {
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "original_quotation": quotation,
                        "assessment_context": field,
                        "ranked_pdf_passages": [
                            {"rank": p["rank"], "text": p["text"]} for p in ranked
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "max_tokens": int(os.environ.get("GROUNDING_MAX_TOKENS", "4096")),
        "temperature": float(os.environ.get("GROUNDING_TEMPERATURE", "0")),
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "pdf_quotations",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "quotations": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        }
                    },
                    "required": ["quotations"],
                    "additionalProperties": False,
                },
            },
        },
    }


def invoke(request, endpoint):
    import requests
    from django.conf import settings

    # requests has no retries by default. Never use a retrying SDK inference call.
    response = requests.post(
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        + "/chat/completions",
        json={"model": endpoint, **request},
        headers={"Authorization": "Bearer " + settings.OPENAI_API_KEY},
        timeout=180,
    )
    try:
        return {
            "http_status": response.status_code,
            "response": response.json(),
            "request_id": response.headers.get("x-request-id"),
        }
    finally:
        response.close()


def quotations_from_response(response):
    if response["http_status"] != 200:
        raise ValueError("Quotation repair endpoint returned a failure")
    response = json.loads(json.dumps(response["response"]))
    if len(response["choices"]) != 1:
        raise ValueError("Quotation repair requires one final answer")
    choice = response["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("Incomplete quotation repair response")
    value = json.loads(choice["message"]["content"])
    if not isinstance(value, dict) or set(value) != {"quotations"}:
        raise ValueError("Invalid quotation repair response")
    return value["quotations"]


def repair_machine_finding(datacell, *, invoke_fn=None):
    from django.db import transaction
    from django.utils import timezone

    from opencontractserver.extracts.models import Datacell
    from opencontractserver.extracts.services.quotation_evidence import (
        finding_evidence,
        finding_identity,
    )

    if os.environ.get("GROUNDING_ENABLED", "true").lower() != "true":
        return
    invoke_fn = invoke_fn or invoke
    finding_evidence(datacell)
    datacell.refresh_from_db()
    if datacell.corrected_data is not None:
        return
    saved = (datacell.evidence_anchors or {}).get("original", {})
    eligible = [
        q for q in saved.get("quotes", []) if q["status"] in {"unmatched", "ambiguous"}
    ]
    if not eligible:
        return
    passages = source_inventory(datacell.document)
    if not passages:
        return
    inventory_hash = hashlib.sha256(
        json.dumps(passages, sort_keys=True).encode()
    ).hexdigest()
    endpoint = os.environ.get("GROUNDING_MODEL", "gpt-4.1-mini")
    for selection in eligible:
        key = hashlib.sha256(
            (saved["fingerprint"] + selection["selectionPath"]).encode()
        ).hexdigest()
        ranked = rank_passages(passages, selection["quote"])
        request = request_for(selection["quote"], datacell.column.name, ranked)
        with transaction.atomic():
            cell = Datacell.objects.select_for_update().get(pk=datacell.pk)
            cache = dict(cell.evidence_anchors or {})
            if (
                cell.corrected_data is not None
                or finding_identity(cell)[3] != saved["fingerprint"]
                or cache.get("original", {}).get("fingerprint") != saved["fingerprint"]
            ):
                return
            attempts = dict(cache.get("machineRepairs", {}))
            if key in attempts:
                continue  # Completed, failed and unknown invocations all retain their admission.
            attempts[key] = {
                "state": "invoking",
                "fingerprint": saved["fingerprint"],
                "selectionPath": selection["selectionPath"],
                "source": saved["source"],
                "inventoryHash": inventory_hash,
                "endpoint": endpoint,
                "request": request,
                "ranked": ranked,
                "attempt": 1,
                "startedAt": timezone.now().isoformat(),
            }
            cache["machineRepairs"] = attempts
            cell.evidence_anchors = cache
            cell.save(update_fields=["evidence_anchors"])
        response, error = None, None
        try:
            response = invoke_fn(request, endpoint)
        except Exception as exc:
            error = type(exc).__name__
            logger.warning(
                "Quotation repair unavailable for cell %s (%s)", cell.pk, error
            )
        # Commit the raw envelope before any parsing or annotation projection.
        with transaction.atomic():
            cell = Datacell.objects.select_for_update().get(pk=datacell.pk)
            cache = dict(cell.evidence_anchors or {})
            attempt = cache["machineRepairs"][key]
            attempt.update(
                state="responded" if response is not None else "unresolved",
                response=response,
                error=error,
                finishedAt=timezone.now().isoformat(),
            )
            cell.evidence_anchors = cache
            cell.save(update_fields=["evidence_anchors"])
    finding_evidence(datacell)


def project_repairs(cell, saved, quotes):
    """Project saved responses only; callers hold the cell lock. No inference."""
    from django.db import transaction

    from opencontractserver.annotations.compact_json import compact_annotation_json
    from opencontractserver.annotations.models import (
        TOKEN_LABEL,
        Annotation,
        AnnotationLabel,
    )
    from opencontractserver.extracts.services.quotation_evidence import (
        quotation_metadata,
    )

    attempts = (cell.evidence_anchors or {}).get("machineRepairs", {})
    if not attempts or cell.corrected_data is not None:
        return quotes
    result = []
    for selection in quotes:
        if selection["status"] not in {"unmatched", "ambiguous"}:
            result.append(selection)
            continue
        attempt = next(
            (
                a
                for a in attempts.values()
                if a.get("fingerprint") == saved["fingerprint"]
                and a.get("selectionPath") == selection["selectionPath"]
                and a.get("state") == "responded"
            ),
            None,
        )
        if attempt is None:
            result.append(selection)
            continue
        try:
            passages = source_inventory(cell.document)
            digest = hashlib.sha256(
                json.dumps(passages, sort_keys=True).encode()
            ).hexdigest()
            if digest != attempt["inventoryHash"]:
                raise ValueError("Retained passage inventory changed")
            excerpts = ground_quotations(
                quotations_from_response(attempt["response"]),
                attempt["ranked"],
                passages,
            )
            if not excerpts:
                raise ValueError("Replacement quotation has no unique retained words")
            with transaction.atomic():
                label, _ = AnnotationLabel.objects.get_or_create(
                    text=(
                        "OC_EXTRACT_SOURCE"
                        if cell.extract.corpus.workflow_label_policy
                        else "Quotation evidence"
                    ),
                    label_type=TOKEN_LABEL,
                    creator_id=cell.creator_id,
                    defaults={"color": "#64748b"},
                )
                projected = []
                for excerpt in excerpts:
                    by_page: dict[int, list[dict]] = {}
                    for word in excerpt["words"]:
                        by_page.setdefault(word["page"], []).append(word)
                    for page, words in by_page.items():
                        payload = compact_annotation_json(
                            {
                                str(page): {
                                    "bounds": {
                                        key: aggregate(w["bounds"][key] for w in words)
                                        for key, aggregate in (
                                            ("left", min),
                                            ("top", min),
                                            ("right", max),
                                            ("bottom", max),
                                        )
                                    },
                                    "tokensJsons": [
                                        {"pageIndex": page, "tokenIndex": w["token"]}
                                        for w in words
                                    ],
                                }
                            }
                        )
                        raw = " ".join(w["text"] for w in words)
                        annotation, _ = Annotation.objects.get_or_create(
                            document_id=cell.document_id,
                            corpus_id=cell.extract.corpus_id,
                            annotation_label=label,
                            annotation_type=TOKEN_LABEL,
                            creator_id=cell.creator_id,
                            page=page,
                            raw_text=raw,
                            json=payload,
                            structural=False,
                            is_grounding_source=False,
                            data__quotationEvidence__datacellId=cell.pk,
                            defaults={"data": quotation_metadata(cell)},
                        )
                        cell.sources.add(annotation)
                        projected.append(
                            {
                                **selection,
                                "quote": excerpt["quote"] if len(by_page) == 1 else raw,
                                "status": "matched",
                                "matchType": "exact",
                                "locatedPage": page + 1,
                                "annotationId": annotation.pk,
                                "annotationIds": [annotation.pk],
                            }
                        )
            result.extend(projected)
        except Exception:
            logger.warning(
                "Saved quotation repair could not be projected for cell %s",
                cell.pk,
                exc_info=True,
            )
            result.append(selection)
    return result


async def ground_machine_extraction(datacell, document, corpus, user_id, **kwargs):
    from asgiref.sync import sync_to_async

    from opencontractserver.extracts.services.quotation_evidence import finding_sources

    await sync_to_async(repair_machine_finding)(datacell)
    return await sync_to_async(lambda: list(finding_sources(datacell)))()
