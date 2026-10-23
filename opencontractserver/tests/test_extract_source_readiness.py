"""Extraction admission must require only passages the indexer can embed."""

from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from opencontractserver.annotations.models import (
    Annotation,
    Embedding,
    StructuralAnnotationSet,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, PipelineSettings
from opencontractserver.extracts.services.source_readiness import document_readiness

EMBEDDER = "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
INDEX_INCOMPLETE = (
    "Document retrieval index is incomplete. Wait for indexing before extracting."
)
BLANK_PASSAGES = (
    " \t\n\f",
    chr(0x00A0),
    chr(0x3000),
    chr(0x2028) + chr(0x00A0) + chr(0x205F),
)


class ExtractSourceReadinessTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        setting = override_settings(MEDIA_ROOT=media.name)
        setting.enable()
        self.addCleanup(setting.disable)
        self.user = get_user_model().objects.create_user(username="extract-readiness")
        pipeline = PipelineSettings.get_instance(use_cache=False)
        pipeline.default_embedder = EMBEDDER
        pipeline.enabled_components = []
        pipeline.save()
        self.corpus = Corpus.objects.create(title="Sources", creator=self.user)
        self.document = Document.objects.create(
            title="Agreement",
            creator=self.user,
            file_type="text/plain",
            backend_lock=False,
            processing_status="completed",
            txt_extract_file=ContentFile(b"A retained clause.", name="source.txt"),
        )

    def passages(self, *, shared=False):
        scope: dict[str, Document | StructuralAnnotationSet] = {
            "document": self.document
        }
        if shared:
            structural_set = StructuralAnnotationSet.objects.create(
                content_hash="extract-readiness-shared", creator=self.user
            )
            self.document.structural_annotation_set = structural_set
            self.document.save(update_fields=["structural_annotation_set"])
            scope = {"structural_set": structural_set}
        parent = Annotation.objects.create(
            **scope, creator=self.user, structural=True, raw_text=BLANK_PASSAGES[0]
        )
        child = Annotation.objects.create(
            **scope,
            creator=self.user,
            structural=True,
            parent=parent,
            raw_text="A retained clause.",
        )
        # Real stored vectors, without invoking any embedding provider.
        Embedding.objects.create(
            annotation=child,
            creator=self.user,
            embedder_path=EMBEDDER,
            vector_384=[0.1] * 384,
        )
        return parent, child

    def assert_blank_parent_is_ready(self, parent, documents):
        for blank in BLANK_PASSAGES:
            parent.raw_text = blank
            parent.save(update_fields=["raw_text"])
            for document in documents:
                with self.subTest(blank=repr(blank), document=document.pk):
                    self.assertIsNone(document_readiness(document, self.corpus.pk))
        self.assertFalse(Embedding.objects.filter(annotation=parent).exists())

    def test_document_owned_blank_parent_does_not_block_indexed_child(self):
        parent, _ = self.passages()
        self.assert_blank_parent_is_ready(parent, [self.document])

    def test_shared_blank_parent_does_not_block_document_or_corpus_copy(self):
        parent, _ = self.passages(shared=True)
        copy = Document.objects.create(
            title="Corpus copy",
            creator=self.user,
            file_type="text/plain",
            backend_lock=False,
            processing_status="completed",
            txt_extract_file=self.document.txt_extract_file,
            structural_annotation_set=self.document.structural_annotation_set,
        )
        self.assert_blank_parent_is_ready(parent, [self.document, copy])

    def test_missing_nonblank_vector_still_blocks(self):
        _, child = self.passages(shared=True)
        Embedding.objects.filter(annotation=child).delete()
        self.assertEqual(
            document_readiness(self.document, self.corpus.pk), INDEX_INCOMPLETE
        )

    def test_only_blank_structural_passages_are_unavailable(self):
        _, child = self.passages()
        child.delete()
        self.assertEqual(
            document_readiness(self.document, self.corpus.pk),
            "Document passages are unavailable. Reprocess the source before extracting.",
        )
