"""Deterministic native labels from domain-owned, verified workflow policies."""

import hashlib
import json
import re

from databricks_port.workflows import (
    TOKEN,
    package,
    resolve_label_policy,
    resolve_response_model,
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def bind_label_policy(corpus, package_hash, *, source_identities=None):
    """Attach an explicit approved policy to an analysis corpus, preserving definitions."""
    from django.db import transaction

    manifest, policy = resolve_label_policy(package_hash)
    if corpus.label_set_id is None:
        raise ValueError(
            "Install the workflow's native corpus label set before binding its policy"
        )
    previous = corpus.workflow_label_policy or {}
    if previous and (
        previous["identity"] != manifest["identity"]
        or previous["owner"] != manifest["owner"]
    ):
        raise ValueError("Corpus is bound to another workflow owner or identity")
    identities = dict(previous.get("sourceIdentities", {}))
    for sha, identity in (source_identities or {}).items():
        if (
            not re.fullmatch(r"[0-9a-f]{64}", sha)
            or not isinstance(identity, dict)
            or identity.get("verified") is not True
            or not identity.get("kind")
            or not identity.get("source_key")
            or not identity.get("provenance")
        ):
            raise ValueError(
                "Source identities require verified SHA-256, kind, source key and provenance"
            )
        identities[sha] = identity
    native = {
        (label.text, label.label_type): label
        for label in corpus.label_set.annotation_labels.all()
    }
    label_ids = {}
    for definition in manifest["labels"]:
        label = native.get((definition["text"], definition["label_type"]))
        if label is None:
            raise ValueError(
                "Corpus label set does not contain the policy package's native definitions"
            )
        label_ids[definition["key"]] = label.pk
    binding = {
        "packageHash": package_hash,
        "identity": manifest["identity"],
        "owner": manifest["owner"],
        "version": manifest["version"],
        "policyVersion": policy["version"],
        "labelIds": label_ids,
        "sourceIdentities": identities,
    }
    with transaction.atomic():
        corpus.workflow_label_policy = binding
        corpus.save(update_fields=["workflow_label_policy"])
    return binding


def _path(value, path):
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _association(
    cell, binding, version, value, source, *, kind, label_key, selection=None
):
    result = {
        "kind": kind,
        "packageHash": binding["packageHash"],
        "workflowIdentity": binding["identity"],
        "workflowOwner": binding["owner"],
        "corpusId": cell.extract.corpus_id,
        "runId": cell.extract_id,
        "datacellId": cell.pk if kind != "source" else None,
        "findingVersion": version,
        "findingFingerprint": fingerprint(value) if kind != "source" else None,
        "responseDefinition": cell.data_definition if kind != "source" else None,
        "source": source,
        "labelKey": label_key,
        "selection": selection,
    }
    result["associationId"] = fingerprint(result)
    result["active"] = True
    return result


def _annotate(
    cell, label, payload, page, raw_text, source, association, *, quote=False
):
    from opencontractserver.annotations.compact_json import compact_annotation_json
    from opencontractserver.annotations.models import Annotation

    source_key = fingerprint(source)
    payload = (
        compact_annotation_json(payload)
        if label.label_type == "TOKEN_LABEL"
        else payload
    )
    annotation, _ = Annotation.objects.get_or_create(
        document_id=cell.document_id,
        corpus_id=cell.extract.corpus_id,
        annotation_label=label,
        annotation_type=label.label_type,
        page=page,
        raw_text=raw_text,
        creator_id=cell.creator_id,
        structural=False,
        is_grounding_source=False,
        json=payload,
        data__domainEvidence__sourceFingerprint=source_key,
        defaults={
            "data": {
                "domainEvidence": {
                    "managed": True,
                    "sourceFingerprint": source_key,
                    "associations": [],
                }
            }
        },
    )
    data = dict(annotation.data or {})
    provenance = dict(data["domainEvidence"])
    associations = {
        item["associationId"]: item for item in provenance.get("associations", [])
    }
    associations[association["associationId"]] = association
    provenance.update(
        associations=list(associations.values()),
        active=True,
        isEvidenceQuote=quote or provenance.get("isEvidenceQuote", False),
    )
    data["domainEvidence"] = provenance
    if data != annotation.data:
        annotation.data = data
        annotation.save(update_fields=["data"])
    if association["datacellId"] is not None:
        cell.sources.add(annotation)
    return annotation


def _deactivate_superseded(cell, current_ids, binding, source):
    """Retain historical associations and reviewer data while hiding superseded labels."""
    from opencontractserver.annotations.models import Annotation

    annotations = Annotation.objects.filter(
        document_id=cell.document_id,
        corpus_id=cell.extract.corpus_id,
        data__domainEvidence__managed=True,
    )
    for annotation in annotations:
        data = dict(annotation.data)
        provenance = dict(data["domainEvidence"])
        changed = False
        associations = []
        for saved in provenance["associations"]:
            item = dict(saved)
            same_workflow = (
                item.get("workflowIdentity") == binding["identity"]
                and item.get("workflowOwner") == binding["owner"]
            )
            if same_workflow and item.get("source") != source:
                active = False
            elif (
                same_workflow
                and item.get("kind") == "source"
                and item.get("packageHash") != binding["packageHash"]
            ):
                active = False
            elif item.get("datacellId") == cell.pk or (
                same_workflow
                and item.get("kind") == "source"
                and item.get("runId") == cell.extract_id
            ):
                active = item["associationId"] in current_ids
            else:
                active = item.get("active", False)
            if active != item.get("active"):
                changed = changed or item.get("active") != active
                item["active"] = active
            associations.append(item)
        if changed:
            provenance.update(
                associations=associations,
                active=any(item.get("active") for item in associations),
            )
            data["domainEvidence"] = provenance
            annotation.data = data
            annotation.save(update_fields=["data"])


def _source_lines(layer):
    """Recover physical lines from the current token geometry, including final lines."""
    for page, tokens in layer.page_tokens.items():
        start = end = last_y = last_height = None
        rows = layer.tokens_dataframe[layer.tokens_dataframe["Page"] == page]
        for row in rows.itertuples(index=False):
            token = tokens[int(row.Token_Id)]
            token_start = int(row.Char_End) - len(token["text"])
            y, height = float(token["y"]), max(float(token["height"]), 1)
            if start is not None and abs(y - last_y) > 0.5 * max(height, last_height):
                yield page, start, end, layer.doc_text[start:end]
                start = None
            if start is None:
                start = token_start
            end, last_y, last_height = int(row.Char_End), y, height
        if start is not None:
            yield page, start, end, layer.doc_text[start:end]


def ensure_selected_policy(cell):
    """Adopt a verified policy only for the package LabelSet selected by its owner."""
    corpus = cell.extract.corpus if cell.extract_id and cell.extract.corpus_id else None
    binding = corpus.workflow_label_policy if corpus else None
    # Bind only when a user has selected this package's own installed LabelSet.
    # Definitions-only startup itself creates no corpus or analysis binding.
    token = (
        TOKEN.fullmatch(cell.data_definition)
        if isinstance(cell.data_definition, str)
        else None
    )
    if not binding and corpus and corpus.label_set_id and token:
        manifest, _ = package(token[1])
        expected_name = (
            manifest["identity"] + " " + manifest["version"] + " · " + token[1][:12]
        )
        if (
            manifest.get("label_policy")
            and corpus.label_set.title == expected_name
            and corpus.label_set.creator_id == cell.creator_id
        ):
            binding = bind_label_policy(corpus, token[1])
    return binding


def apply_finding_labels(cell, quotes):
    """Project one saved finding through its corpus policy, with no model invocation."""
    from django.db import transaction

    from opencontractserver.annotations.models import (
        Annotation,
        AnnotationLabel,
    )

    corpus = cell.extract.corpus if cell.extract_id and cell.extract.corpus_id else None
    binding = corpus.workflow_label_policy if corpus else None
    binding = ensure_selected_policy(cell)
    if not binding:
        return quotes
    manifest, policy = resolve_label_policy(binding["packageHash"])
    native_labels = AnnotationLabel.objects.in_bulk(binding["labelIds"].values())
    labels = {
        key: native_labels[identifier]
        for key, identifier in binding["labelIds"].items()
    }
    labelset_ids = set(corpus.label_set.annotation_labels.values_list("pk", flat=True))
    if any(label.pk not in labelset_ids for label in labels.values()):
        raise ValueError(
            "Bound policy label no longer belongs to its native corpus label set"
        )
    version = "corrected" if cell.corrected_data is not None else "original"
    raw = cell.corrected_data if version == "corrected" else cell.data
    value = raw.get("data", raw) if isinstance(raw, dict) else raw
    original = (
        TOKEN.fullmatch(cell.data_definition)
        if isinstance(cell.data_definition, str)
        else None
    )
    column_key = original[2] if original else None
    valid = False
    try:
        if original is None:
            raise ValueError(
                "Saved finding has no verified workflow response definition"
            )
        original_manifest, _ = package(original[1])
        if (
            original_manifest["identity"] != binding["identity"]
            or original_manifest["owner"] != binding["owner"]
        ):
            raise ValueError("Saved finding belongs to another workflow")
        model = resolve_response_model(
            f"workflow:{binding['packageHash']}:{column_key}"
        )
        model.model_validate(value)
        valid = cell.failed is None and cell.completed is not None
    except (ValueError, TypeError):
        pass
    document = cell.document
    source = {
        "documentId": document.pk,
        "sourceHash": document.pdf_file_hash,
        "structuralSetId": document.structural_annotation_set_id,
        "pawlsFile": document.pawls_parse_file.name,
        "textFile": document.txt_extract_file.name,
    }
    evidence = policy["evidence"]
    keys = (
        evidence["by_column"].get(column_key, [])
        if valid
        and _path(value, evidence["state_field"]) in evidence["eligible_states"]
        else []
    )
    current_ids, displayed = set(), []
    with transaction.atomic():
        # Serialize same-corpus native projections, including shared evidence
        # from different cells, before get_or_create or association updates.
        type(corpus).objects.select_for_update().get(pk=corpus.pk)
        if policy.get("source_rules"):
            from databricks_port.evidence import normalized_text

            from opencontractserver.utils.span_projection import (
                load_document_text_and_layer,
                project_span_to_token_annotation,
            )

            try:
                text, layer, annotation_type = load_document_text_and_layer(document)
            except (OSError, ValueError):
                layer = None
            if layer is not None and annotation_type == "TOKEN_LABEL":
                for page_number, offset, _, line in _source_lines(layer):
                    for rule in policy["source_rules"]:
                        if (
                            rule.get("max_line_tokens")
                            and len(line.split()) > rule["max_line_tokens"]
                        ):
                            continue
                        expression = re.compile(
                            rule["pattern"],
                            sum(getattr(re, flag) for flag in rule.get("flags", [])),
                        )
                        for match in expression.finditer(line):
                            key = rule["label_key"]
                            association = _association(
                                cell,
                                binding,
                                "source",
                                None,
                                source,
                                kind="source",
                                label_key=key,
                                selection={
                                    "quote": match.group(),
                                    "locatedPage": page_number + 1,
                                },
                            )
                            if rule["kind"] == "document":
                                _annotate(
                                    cell, labels[key], {}, 0, None, source, association
                                )
                                current_ids.add(association["associationId"])
                            else:
                                try:
                                    payload, page, raw_text = (
                                        project_span_to_token_annotation(
                                            layer,
                                            start=offset + match.start(),
                                            end=offset + match.end(),
                                            text=match.group(),
                                            label_text=labels[key].text,
                                        )
                                    )
                                    if (
                                        normalized_text(raw_text)[0]
                                        != normalized_text(match.group())[0]
                                        or page != page_number
                                    ):
                                        continue
                                except ValueError:
                                    continue
                                _annotate(
                                    cell,
                                    labels[key],
                                    payload,
                                    page,
                                    raw_text,
                                    source,
                                    association,
                                )
                                current_ids.add(association["associationId"])
        identity = binding.get("sourceIdentities", {}).get(document.pdf_file_hash, {})
        for rule in policy.get("source_identity_rules", []):
            if (
                identity.get("verified") is True
                and identity.get("kind") == rule["kind"]
            ):
                association = _association(
                    cell,
                    binding,
                    "source",
                    None,
                    source,
                    kind="source",
                    label_key=rule["label_key"],
                    selection={"verifiedIdentity": identity},
                )
                _annotate(
                    cell, labels[rule["label_key"]], {}, 0, None, source, association
                )
                current_ids.add(association["associationId"])
        for quote in quotes:
            projected = dict(quote)
            projected["domainLabels"] = [
                {"key": key, "text": labels[key].text} for key in keys
            ]
            if not keys:
                projected["annotationId"] = None
                projected["annotationIds"] = []
            annotation_ids = []
            if quote.get("annotationId") is not None:
                anchor = Annotation.objects.get(
                    pk=quote["annotationId"], document_id=cell.document_id
                )
                for key in keys:
                    association = _association(
                        cell,
                        binding,
                        version,
                        value,
                        source,
                        kind="quote",
                        label_key=key,
                        selection={
                            name: quote.get(name)
                            for name in (
                                "quote",
                                "reportedPage",
                                "locatedPage",
                                "speaker",
                                "scope",
                                "selectionPath",
                            )
                        },
                    )
                    annotation = _annotate(
                        cell,
                        labels[key],
                        anchor.json,
                        anchor.page,
                        anchor.raw_text,
                        source,
                        association,
                        quote=True,
                    )
                    current_ids.add(association["associationId"])
                    annotation_ids.append(annotation.pk)
            if annotation_ids:
                projected["annotationId"] = annotation_ids[0]
                projected["annotationIds"] = annotation_ids
            displayed.append(projected)
        matched_groups = set()
        if valid:
            for rule in policy.get("finding_document_rules", []):
                if (
                    rule["column_key"] != column_key
                    or _path(value, rule["state_field"]) not in rule["eligible_states"]
                ):
                    continue
                group = rule.get("group")
                if group and group in matched_groups:
                    continue
                field = _path(value, rule["value_path"])
                if not isinstance(field, str):
                    continue
                matches = (
                    field in rule["values"]
                    if rule["match"] == "equals"
                    else any(
                        re.search(
                            r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                            field,
                            re.IGNORECASE,
                        )
                        for term in rule["values"]
                    )
                )
                if matches:
                    key = rule["label_key"]
                    association = _association(
                        cell,
                        binding,
                        version,
                        value,
                        source,
                        kind="document",
                        label_key=key,
                    )
                    _annotate(cell, labels[key], {}, 0, None, source, association)
                    current_ids.add(association["associationId"])
                    if group:
                        matched_groups.add(group)
        _deactivate_superseded(cell, current_ids, binding, source)
    return displayed


def replay_labels(corpus, package_hash, *, extract_ids=None, source_identities=None):
    """Apply an approved policy to saved results, returning reproducible receipts."""
    from databricks_port.finding_evidence import finding_evidence

    from opencontractserver.extracts.models import Datacell

    bind_label_policy(corpus, package_hash, source_identities=source_identities)
    cells = Datacell.objects.filter(extract__corpus=corpus).select_related(
        "document", "column", "extract__corpus"
    )
    if extract_ids is not None:
        cells = cells.filter(extract_id__in=extract_ids)
    results = []
    for cell in cells.order_by("extract_id", "document_id", "column_id", "pk"):
        data_before = fingerprint(
            [cell.data, cell.corrected_data, cell.data_definition]
        )
        review_before = (cell.approved_by_id, cell.rejected_by_id)
        quotes = finding_evidence(cell)
        cell.refresh_from_db(
            fields=[
                "data",
                "corrected_data",
                "data_definition",
                "approved_by",
                "rejected_by",
            ]
        )
        data_preserved = data_before == fingerprint(
            [cell.data, cell.corrected_data, cell.data_definition]
        )
        review_preserved = review_before == (cell.approved_by_id, cell.rejected_by_id)
        if not data_preserved or not review_preserved:
            raise RuntimeError(
                "Label replay changed saved finding data or review state"
            )
        results.append(
            {
                "datacellId": cell.pk,
                "runId": cell.extract_id,
                "version": (
                    "corrected" if cell.corrected_data is not None else "original"
                ),
                "failed": cell.failed is not None,
                "quotations": len(quotes),
                "dataPreserved": data_preserved,
                "reviewPreserved": review_preserved,
                "labelledQuotations": sum(
                    bool(quote.get("annotationIds")) for quote in quotes
                ),
                "locationStates": [quote["status"] for quote in quotes],
            }
        )
    return {
        "corpusId": corpus.pk,
        "policyPackageHash": package_hash,
        "modelCalls": 0,
        "results": results,
    }
