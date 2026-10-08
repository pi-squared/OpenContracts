"""Authenticated independent corpus copies using the native ingestion pipeline."""

import hashlib

from celery import chain
from databricks_port.docling_jobs import PARSER_PATH, WORKER_INSTANCE, timestamp
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from opencontractserver.constants.document_processing import MARKDOWN_MIME_TYPE
from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.tasks.doc_tasks import (
    document_processing_steps,
    mark_doc_failed_on_chain_error,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


def copy_corpus(source_id, title, user):
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 150:
        raise ValidationError("Choose a corpus title between 1 and 150 characters")
    title = title.strip()
    with transaction.atomic():
        source = Corpus.objects.select_for_update().get(pk=source_id)
        if not source.user_can(user, PermissionTypes.READ):
            raise PermissionDenied("Read access to the source corpus is required")
        marker = "Docling job copy of corpus " + str(source.pk)
        existing = Corpus.objects.filter(title=title, creator=user).first()
        if existing:
            if existing.description != marker:
                raise ValidationError("The target corpus title is already in use")
            return existing
        if CorpusAction.objects.filter(
            run_on_all_corpuses=True, disabled=False, trigger="add_document"
        ).exists():
            raise ValidationError(
                "Automatic global assessments must be disabled for this parser-only copy"
            )
        paths = list(
            DocumentPath.objects.filter(
                corpus=source, is_current=True, is_deleted=False
            ).select_related("document")
        )
        if not paths:
            raise ValidationError("The source corpus has no current documents")
        if any(
            p.document.file_type not in ("application/pdf", MARKDOWN_MIME_TYPE)
            for p in paths
        ):
            raise ValidationError(
                "Docling corpus copying supports PDFs and the corpus README"
            )
        if any(not p.document.user_can(user, PermissionTypes.READ) for p in paths):
            raise PermissionDenied("Read access to every source document is required")
        target = Corpus.objects.create(
            title=title,
            description=marker,
            creator=user,
            auto_branding_enabled=False,
            label_set=source.label_set,
            preferred_embedder=source.preferred_embedder,
            preferred_llm=source.preferred_llm,
            workflow_label_policy=source.workflow_label_policy,
        )
        set_permissions_for_obj_to_user(user, target, [PermissionTypes.CRUD])
        for record in paths:
            original = record.document
            is_pdf = original.file_type == "application/pdf"
            file = original.pdf_file if is_pdf else original.txt_extract_file
            with file.open("rb") as stream:
                content = stream.read()
            source_hash = hashlib.sha256(content).hexdigest()
            metadata = {
                "docling_copy": {
                    "source_corpus_id": source.pk,
                    "source_document_id": original.pk,
                    "source_sha256": source_hash,
                }
            }
            if is_pdf:
                metadata["databricks_pdf_parser"] = PARSER_PATH
            copied, _, _ = target.import_content(
                user=user,
                content=content,
                path=record.path,
                file_type=original.file_type,
                title=original.title,
                description=original.description,
                processing_started=timezone.now(),
                backend_lock=True,
                processing_status="pending",
                custom_meta=metadata,
            )
            copied.source_document = original
            copied.save(update_fields=["source_document"])
            set_permissions_for_obj_to_user(user, copied, [PermissionTypes.CRUD])
            if is_pdf:
                transaction.on_commit(lambda doc_id=copied.pk: enqueue(user.pk, doc_id))
            else:
                copied.backend_lock = False
                copied.processing_status = "completed"
                copied.processing_finished = timezone.now()
                copied.save(
                    update_fields=[
                        "backend_lock",
                        "processing_status",
                        "processing_finished",
                    ]
                )
                if source.readme_caml_document_id == original.pk:
                    target.readme_caml_document = copied
                    target.save(update_fields=["readme_caml_document"])
        return target


def enqueue(user_id, doc_id):
    with transaction.atomic():
        doc = Document.objects.select_for_update().get(pk=doc_id)
        metadata = doc.custom_meta or {}
        dispatch = metadata.get("docling_dispatch") or {}
        if doc.processing_status == "completed" or (
            dispatch.get("worker_instance") == WORKER_INSTANCE
            and doc.processing_status in ("pending", "processing")
        ):
            return
        task = chain(*document_processing_steps(user_id=user_id, doc_id=doc_id))
        task.freeze()
        doc.custom_meta = {
            **metadata,
            "docling_dispatch": {
                "worker_instance": WORKER_INSTANCE,
                "admitted_at": timestamp(),
                "task_id": task.id,
            },
        }
        doc.processing_status = "pending"
        doc.processing_error = ""
        doc.processing_finished = None
        doc.backend_lock = True
        doc.save(
            update_fields=[
                "custom_meta",
                "processing_status",
                "processing_error",
                "processing_finished",
                "backend_lock",
            ]
        )
        transaction.on_commit(
            lambda: task.apply_async(
                link_error=mark_doc_failed_on_chain_error.s(doc_id=doc_id)
            )
        )


def status(corpus, user):
    rows = []
    for path in DocumentPath.objects.filter(
        corpus=corpus, is_current=True, is_deleted=False
    ).select_related("document"):
        doc = path.document
        if not doc.user_can(user, PermissionTypes.READ):
            raise PermissionDenied("Read access to every corpus document is required")
        metadata = doc.custom_meta or {}
        job = metadata.get("docling_job") or {}
        rows.append(
            {
                "id": doc.pk,
                "title": doc.title,
                "file_type": doc.file_type,
                "status": doc.processing_status,
                "page_count": doc.page_count,
                "parser": metadata.get("parser"),
                "parser_version": metadata.get("parser_version"),
                "run_id": job.get("run_id"),
                "attempt_id": job.get("attempt_id"),
                "source_document_id": doc.source_document_id,
                "source_sha256": (metadata.get("docling_copy") or {}).get(
                    "source_sha256"
                ),
                "has_parse_artifact": bool(metadata.get("parsing_artifact_sha256")),
                "error": doc.processing_error,
            }
        )
    return {
        "corpus_id": corpus.pk,
        "title": corpus.title,
        "slug": corpus.slug,
        "documents": rows,
    }


class DoclingCorpusCopy(APIView):
    def post(self, request):
        import os

        if not os.environ.get("DOCLING_JOB_ID") or not os.environ.get(
            "DOCLING_ARTIFACT_ROOT"
        ):
            raise ValidationError("Docling job resources are not configured")
        source_id = request.data.get("source_corpus_id")
        if not isinstance(source_id, int) or isinstance(source_id, bool):
            raise ValidationError("Supply a numeric source_corpus_id")
        try:
            corpus = copy_corpus(source_id, request.data.get("title"), request.user)
        except Corpus.DoesNotExist:
            raise ValidationError("Source corpus does not exist") from None
        return Response(status(corpus, request.user), status=202)


class DoclingCorpusStatus(APIView):
    def get(self, request, corpus_id):
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            raise ValidationError("Corpus does not exist") from None
        if not corpus.user_can(request.user, PermissionTypes.READ):
            raise PermissionDenied("Read access to this corpus is required")
        return Response(status(corpus, request.user))

    def post(self, request, corpus_id):
        """Explicitly recover incomplete sources using their admitted job attempts."""
        try:
            corpus = Corpus.objects.get(pk=corpus_id)
        except Corpus.DoesNotExist:
            raise ValidationError("Corpus does not exist") from None
        if not corpus.user_can(request.user, PermissionTypes.UPDATE):
            raise PermissionDenied("Edit access to this corpus is required")
        rows = DocumentPath.objects.filter(
            corpus=corpus, is_current=True, is_deleted=False
        ).select_related("document")
        rows = list(rows)
        for record in rows:
            if not record.document.user_can(request.user, PermissionTypes.READ):
                raise PermissionDenied(
                    "Read access to every corpus document is required"
                )
            if not record.document.user_can(request.user, PermissionTypes.UPDATE):
                raise PermissionDenied(
                    "Edit access to every corpus document is required"
                )
        for record in rows:
            doc = record.document
            metadata = doc.custom_meta or {}
            if (
                metadata.get("databricks_pdf_parser") != PARSER_PATH
                or doc.processing_status == "completed"
            ):
                continue
            job_state = (metadata.get("docling_job") or {}).get("job_state", {})
            if job_state.get("result_state") not in (None, "SUCCESS"):
                continue
            enqueue(request.user.pk, doc.pk)
        return Response(status(corpus, request.user), status=202)
