"""Native API authorization and active-dispatch controls in a prepared runtime."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch


@unittest.skipUnless(
    os.environ.get("DOCLING_NATIVE_CONTROLS"),
    "Requires initialized native Django runtime",
)
class NativeDoclingControls(unittest.TestCase):
    def setUp(self):
        from databricks_port import docling_corpus
        from rest_framework.test import APIRequestFactory

        from opencontractserver.types.enums import PermissionTypes

        self.module = docling_corpus
        self.permissions = PermissionTypes
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(pk=1, is_authenticated=True)
        self.corpus = SimpleNamespace(pk=9, user_can=lambda user, permission: True)

    def request(self, method):
        from rest_framework.test import force_authenticate

        request = getattr(self.factory, method)("/port/docling/corpora/9")
        force_authenticate(request, self.user)
        return request

    def test_corpus_read_does_not_reveal_denied_document(self):
        doc = SimpleNamespace(user_can=lambda user, permission: False)
        with patch.object(
            self.module.Corpus.objects, "get", return_value=self.corpus
        ), patch.object(self.module.DocumentPath.objects, "filter") as paths:
            paths.return_value.select_related.return_value = [
                SimpleNamespace(document=doc)
            ]
            response = self.module.DoclingCorpusStatus.as_view()(
                self.request("get"), corpus_id=9
            )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("documents", response.data)

    def test_recovery_checks_all_document_grants_before_enqueuing(self):
        allowed = SimpleNamespace(user_can=lambda user, permission: True)
        denied = SimpleNamespace(
            user_can=lambda user, permission: permission == self.permissions.READ
        )
        with patch.object(
            self.module.Corpus.objects, "get", return_value=self.corpus
        ), patch.object(
            self.module.DocumentPath.objects, "filter"
        ) as paths, patch.object(
            self.module, "enqueue"
        ) as enqueue:
            paths.return_value.select_related.return_value = [
                SimpleNamespace(document=allowed),
                SimpleNamespace(document=denied),
            ]
            response = self.module.DoclingCorpusStatus.as_view()(
                self.request("post"), corpus_id=9
            )
        self.assertEqual(response.status_code, 403)
        enqueue.assert_not_called()

    def test_active_dispatch_is_not_reset_or_queued_again(self):
        doc = SimpleNamespace(
            processing_status="processing",
            custom_meta={
                "docling_dispatch": {"worker_instance": self.module.WORKER_INSTANCE},
            },
        )
        with patch.object(
            self.module.Document.objects, "select_for_update"
        ) as documents, patch.object(self.module, "chain") as chain:
            documents.return_value.get.return_value = doc
            self.module.enqueue(self.user.pk, 99)
        chain.assert_not_called()
