"""Retained source fixtures for extraction tests with ingestion signals disabled."""

import hashlib
import json
import os
from functools import wraps
from pathlib import Path
from typing import get_origin
from unittest.mock import AsyncMock, patch

from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone

from opencontractserver.annotations.models import Annotation, Embedding
from opencontractserver.extracts.services.source_readiness import ensure_document_ready
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.embedding_identity import embeddable_annotations

TEST_EMBEDDER = "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"


async def fake_structured_response(*args, target_type=str, **kwargs):
    """Deterministic agent boundary for primitive task/orchestration tests."""
    if get_origin(target_type) is list:
        return ["payment", "delivery"], []
    if target_type is bool:
        return True, []
    return "Test Document", []


def replay_extraction(cassette_name, *, expected_interactions):
    """Run the real task/API/SDK and require consumption of retained responses.

    The legacy cassettes match the method and URL. They exercise protocol and
    typed value marshalling, rather than the accuracy of their recorded values.
    Unmatched requests fail: these tests can never record a replacement.
    """

    def decorate(method):
        @wraps(method)
        def replay(self, *args, **kwargs):
            import vcr

            from opencontractserver.extracts.models import Datacell
            from opencontractserver.llms.api import AgentAPI

            self.corpus.preferred_llm = "openai:gpt-4o-mini"
            self.corpus.save(update_fields=["preferred_llm"])
            path = (
                Path(__file__).resolve().parents[2]
                / "fixtures/vcr_cassettes"
                / cassette_name
            )
            original_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            existing_cells = set(Datacell.objects.values_list("pk", flat=True))
            real_api = AgentAPI.get_structured_response_and_sources_from_document
            # A spy delegates to the actual API; cassette consumption below
            # fails if a fake result is accidentally substituted later.
            with patch.dict(
                os.environ, {"OPENAI_API_KEY": "test-vcr-no-provider"}
            ), patch.object(
                AgentAPI,
                "get_structured_response_and_sources_from_document",
                new=AsyncMock(wraps=real_api),
            ) as self.agent, vcr.use_cassette(
                str(path),
                record_mode="none",
                filter_headers=["authorization"],
                allow_playback_repeats=False,
            ) as cassette:
                result = method(self, *args, **kwargs)
                self.assertEqual(self.agent.await_count, expected_interactions)
                self.assertTrue(
                    all(
                        call.kwargs["model"] == "openai:gpt-4o-mini"
                        for call in self.agent.await_args_list
                    )
                )
                self.assertEqual(len(cassette), expected_interactions)
                self.assertEqual(cassette.play_count, expected_interactions)
                self.assertTrue(cassette.all_played)
                cells = Datacell.objects.exclude(pk__in=existing_cells).select_related(
                    "column"
                )
                self.assertEqual(cells.count(), expected_interactions)
                for cell in cells:
                    self.assertIsNotNone(cell.completed)
                    self.assertIsNone(cell.failed)
                    value = cell.data["data"]
                    if cell.column.extract_is_list:
                        self.assertIsInstance(value, list)
                        self.assertTrue(all(isinstance(item, str) for item in value))
                    elif cell.column.output_type == "bool":
                        self.assertIsInstance(value, bool)
                    else:
                        self.assertIsInstance(value, str)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), original_hash
            )
            return result

        return replay

    return decorate


def prepare_extraction_source(document, corpus, *, text=None):
    """Supply real lifecycle/text/passage/index rows without a provider call.

    Call this on the corpus-isolated document returned by ``add_document``.
    PDF fixtures keep their actual PAWLS pages; new text fixtures use their
    supplied text. Readiness itself remains unpatched and validates the result.
    """
    from opencontractserver.pipeline.embedders.test_embedder import TestEmbedder

    corpus.preferred_embedder = TEST_EMBEDDER
    corpus.save(update_fields=["preferred_embedder"])
    if text is not None:
        document.txt_extract_file.save(
            f"extraction-source-{document.pk}.txt",
            ContentFile(text.encode()),
            save=False,
        )
    with document.txt_extract_file.open("r") as stream:
        retained_text = stream.read()
    if not retained_text.strip():
        raise ValueError("A ready extraction fixture needs nonempty retained text")

    pages = []
    if document.file_type == "application/pdf":
        with document.pawls_parse_file.open("r") as stream:
            pages = expand_pawls_pages(json.load(stream))
        # Legacy fixture PAWLS files explicitly enumerate 1..N. Materialize a
        # new fixture-local copy in the parser's zero-based format; leave the
        # shipped files and malformed/partial coverage cases unchanged.
        if [p["page"]["index"] for p in pages] == list(range(1, len(pages) + 1)):
            for index, page in enumerate(pages):
                page["page"]["index"] = index
            document.pawls_parse_file.save(
                f"extraction-pages-{document.pk}.json",
                ContentFile(json.dumps(pages).encode()),
                save=False,
            )
        document.page_count = len(pages)
    document.processing_status = "completed"
    document.backend_lock = False
    document.processing_started = document.processing_started or timezone.now()
    document.processing_finished = timezone.now()
    document.save()

    scope = Q(document=document, structural=True)
    if document.structural_annotation_set_id:
        scope |= Q(
            structural_set_id=document.structural_annotation_set_id, structural=True
        )
    passages = embeddable_annotations(Annotation.objects.filter(scope))
    if not passages.exists():
        owner = (
            {"structural_set_id": document.structural_annotation_set_id}
            if document.structural_annotation_set_id
            else {"document": document}
        )
        content = (
            [
                (p["page"]["index"], " ".join(t["text"] for t in p["tokens"]))
                for p in pages
            ]
            if pages
            else [(0, retained_text)]
        )
        for page_index, passage_text in content:
            if passage_text.strip():
                Annotation.objects.create(
                    **owner,
                    creator=document.creator,
                    structural=True,
                    raw_text=passage_text,
                    page=page_index,
                )
    embedder = TestEmbedder()
    for passage in embeddable_annotations(Annotation.objects.filter(scope)):
        Embedding.objects.update_or_create(
            annotation=passage,
            embedder_path=TEST_EMBEDDER,
            defaults={
                "creator": document.creator,
                "vector_384": embedder.embed_text(passage.raw_text),
            },
        )
    ensure_document_ready(document, corpus.pk)
