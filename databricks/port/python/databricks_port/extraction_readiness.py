"""One source readiness rule for native admission, queued work and review UI."""

import json

from asgiref.sync import sync_to_async
from django.db.models import Q


class SourceNotReady(ValueError):
    """An extraction source has no complete, searchable evidence."""


def document_readiness(document, corpus_id=None):
    """Return a safe user-facing reason, or None when evidence is ready.

    No model or embedding request is made. Resolve the same configured embedder
    and vector dimension as retrieval, and require an index for every retained
    structural text passage, including shared sets used by corpus copies.
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.documents.models import DocumentPath
    from opencontractserver.pipeline.utils import get_embedder_instance
    from opencontractserver.utils.compact_pawls import expand_pawls_pages
    from opencontractserver.utils.embeddings import get_embedder

    if document.processing_status == "failed":
        return "Document processing failed. Open the original PDF and reprocess the source before extracting."
    if document.processing_status != "completed" or document.backend_lock:
        return (
            "Document processing is incomplete. Wait for processing before extracting."
        )
    try:
        if not document.txt_extract_file:
            return (
                "Document text is unavailable. Reprocess the source before extracting."
            )
        with document.txt_extract_file.open("r") as stream:
            if not stream.read().strip():
                return "Document text is empty. Reprocess the source before extracting."
        if document.file_type == "application/pdf":
            if not document.pawls_parse_file or document.page_count < 1:
                return "Document PDF evidence is incomplete. Reprocess the source before extracting."
            with document.pawls_parse_file.open("r") as stream:
                pages = expand_pawls_pages(json.load(stream))
            if len(pages) != document.page_count or [
                p["page"]["index"] for p in pages
            ] != list(range(document.page_count)):
                return "Document PDF page coverage is incomplete. Reprocess the source before extracting."
            if not any(p["tokens"] for p in pages):
                return "Document PDF evidence is empty. Reprocess the source before extracting."
    except (OSError, ValueError, KeyError, TypeError):
        return (
            "Document evidence cannot be read. Reprocess the source before extracting."
        )
    scope = Q(document_id=document.pk, structural=True)
    if document.structural_annotation_set_id:
        scope |= Q(
            structural_set_id=document.structural_annotation_set_id, structural=True
        )
    passages = (
        Annotation.objects.filter(scope)
        .exclude(raw_text="")
        .exclude(raw_text__isnull=True)
    )
    if not passages.exists():
        return (
            "Document passages are unavailable. Reprocess the source before extracting."
        )
    if corpus_id is None:
        corpus_id = (
            DocumentPath.objects.filter(document_id=document.pk)
            .values_list("corpus_id", flat=True)
            .first()
        )
    embedder_class, path = get_embedder(corpus_id=corpus_id)
    if not embedder_class or not path:
        return "Document retrieval index is unavailable. Check the embedding configuration."
    dimension = get_embedder_instance(embedder_class, path).vector_size
    indexed = passages.filter(
        **{
            "embedding_set__embedder_path": path,
            f"embedding_set__vector_{dimension}__isnull": False,
        }
    ).values("pk")
    if passages.exclude(pk__in=indexed).exists():
        return "Document retrieval index is incomplete. Wait for indexing before extracting."
    return None


def ensure_document_ready(document, corpus_id=None):
    # Reload lifecycle fields to catch a stale queued task or ORM instance.
    document.refresh_from_db()
    reason = document_readiness(document, corpus_id)
    if reason:
        raise SourceNotReady(reason)


aensure_document_ready = sync_to_async(ensure_document_ready)


def ensure_extract_ready(extract):
    documents = list(extract.documents.all())
    if not documents:
        raise SourceNotReady("Add a processed document before extracting.")
    for document in documents:
        ensure_document_ready(document, extract.corpus_id)
