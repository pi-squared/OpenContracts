"""Pure annotation visibility and lazy compatibility imports for native services.

AnnotationService imports this predicate while its package initializes. Resolve
persistence services lazily to keep that native initialization cycle well formed.
"""

import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def active_domain_annotation_filter():
    """Keep ordinary annotations and domain annotations whose labels are active.

    PostgreSQL's missing JSON keys need an explicit branch so unmanaged
    reviewer annotations remain visible alongside active domain evidence.
    """
    from django.db.models import Q

    return Q(data__domainEvidence__active__isnull=True) | ~Q(
        data__domainEvidence__active=False
    )


def association_visible(item, values, versions=None):
    """Resolve one association against its owning finding's displayed version."""
    from opencontractserver.extracts.services.evidence_text import (
        finding_outcome,
        selected_quotes,
    )

    if not item.get("active"):
        return False
    if item.get("kind") == "source":
        return True
    identifier = item.get("datacellId")
    if identifier not in values:
        return False
    value = values[identifier]
    if finding_outcome(value) == "not_found":
        return False
    if versions and item.get("findingVersion") not in (None, versions[identifier]):
        return False
    raw = value.get("data", value) if isinstance(value, dict) else value
    if item.get("findingFingerprint") and item["findingFingerprint"] != fingerprint(
        raw
    ):
        return False
    selection = item.get("selection") or {}
    return item.get("kind") != "quote" or any(
        quote["selectionPath"] == selection.get("selectionPath")
        for quote in selected_quotes(value)
    )


def evidence_annotation_visible(data, values, versions=None, raw_text=None):
    """Evaluate retained associations against effective values, without writes."""
    from opencontractserver.extracts.services.evidence_text import (
        normalized_text,
        selected_quotes,
    )

    data = data or {}
    domain = data.get("domainEvidence", {})
    if domain.get("active") is False:
        return False
    associations = domain.get("associations", [])
    if associations:
        return any(association_visible(item, values, versions) for item in associations)
    quotation = data.get("quotationEvidence", {})
    identifier = quotation.get("datacellId")
    if identifier is not None:
        return (
            quotation.get("active") is not False
            and identifier in values
            and (
                not versions
                or quotation.get("findingVersion") in (None, versions[identifier])
            )
            and isinstance(raw_text, str)
            and any(
                normalized_text(quote["quote"])[0] == normalized_text(raw_text)[0]
                for quote in selected_quotes(values[identifier])
            )
        )
    return True


def filter_finding_annotations(queryset):
    """Batch-load referenced cells for this feed; stale active flags cannot win.

    Return a queryset so native pagination and permission filtering still apply.
    Source-derived and ordinary annotations have independent eligibility.
    """
    from django.db.models import BooleanField, Case, JSONField, Q, Value, When

    from opencontractserver.extracts.models import Datacell

    candidates = list(
        queryset.filter(
            Q(data__domainEvidence__isnull=False)
            | Q(data__quotationEvidence__isnull=False)
        ).values_list("pk", "data", "raw_text")
    )
    identifiers: set[int] = set()
    for _, data, _ in candidates:
        data = data or {}
        identifiers.update(
            item["datacellId"]
            for item in data.get("domainEvidence", {}).get("associations", [])
            if item.get("datacellId") is not None
        )
        identifier = data.get("quotationEvidence", {}).get("datacellId")
        if identifier is not None:
            identifiers.add(identifier)
    cells = list(
        Datacell.objects.filter(pk__in=identifiers).values_list(
            "pk", "data", "corrected_data"
        )
    )
    values = {
        pk: corrected if corrected is not None else original
        for pk, original, corrected in cells
    }
    versions = {
        pk: "corrected" if corrected is not None else "original"
        for pk, _, corrected in cells
    }
    hidden, quote_ids, provenance_cases = [], [], []
    for pk, data, raw_text in candidates:
        if not evidence_annotation_visible(data, values, versions, raw_text):
            hidden.append(pk)
            continue
        domain = dict((data or {}).get("domainEvidence", {}))
        if domain.get("associations"):
            domain["associations"] = [
                item
                for item in domain["associations"]
                if association_visible(item, values, versions)
            ]
            if any(item.get("kind") == "quote" for item in domain["associations"]):
                quote_ids.append(pk)
        elif (data or {}).get("quotationEvidence", {}).get("datacellId"):
            quote_ids.append(pk)
        provenance_cases.append(
            When(pk=pk, then=Value(domain, output_field=JSONField()))
        )
    return queryset.exclude(pk__in=hidden).annotate(
        _eligible_evidence_quote=Case(
            When(pk__in=quote_ids, then=Value(True)),
            default=Value(False),
            output_field=BooleanField(),
        ),
        _projected_domain_provenance=Case(
            *provenance_cases,
            default=Value({}, output_field=JSONField()),
            output_field=JSONField()
        ),
    )


_SERVICE_EXPORTS = {
    "fingerprint",
    "bind_label_policy",
    "ensure_selected_policy",
    "apply_finding_labels",
    "replay_labels",
}


def __getattr__(name):
    if name not in _SERVICE_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module

    return getattr(
        import_module("opencontractserver.annotations.services.domain_evidence"), name
    )
