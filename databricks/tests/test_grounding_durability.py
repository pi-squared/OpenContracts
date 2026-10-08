"""Native QA database controls; require an explicit private QA-only context.

Run after uploading a public PDF to the independent QA App. No provider is called.
The private context must verify the selected QA project before setting up Django.
"""

import json
import os
import runpy
import threading
import unittest
from unittest.mock import patch


@unittest.skipUnless(
    os.environ.get("OPENCONTRACTS_QA_CONTEXT"), "Explicit QA context required"
)
class GroundingDurabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runpy.run_path(os.environ["OPENCONTRACTS_QA_CONTEXT"])
        from django.contrib.auth import get_user_model

        from opencontractserver.documents.models import Document
        from opencontractserver.extracts.services.quotation_grounding import (
            source_inventory,
        )

        cls.user = get_user_model().objects.get(username="pilot-owner")
        cls.document = Document.objects.filter(
            processing_finished__isnull=False
        ).first()
        assert cls.document is not None, "Upload and finish a QA PDF first"
        cls.passages = source_inventory(cls.document)
        candidates = [p["text"] for p in cls.passages if len(p["text"].split()) > 15]
        cls.original_quote = candidates[0]
        cls.human_quote = next(q for q in candidates[1:] if q != cls.original_quote)

    def setUp(self):
        # Embedding dispatch is outside these ORM/repair durability controls.
        dispatch = patch(
            "opencontractserver.annotations.signals._dispatch_annotation_embedding"
        )
        dispatch.start()
        self.addCleanup(dispatch.stop)
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.extracts.models import (
            Column,
            Datacell,
            Extract,
            Fieldset,
        )

        self.corpus = Corpus.objects.create(
            title="Durability control", creator=self.user
        )
        self.fieldset = Fieldset.objects.create(
            name="Durability control", creator=self.user
        )
        self.column = Column.objects.create(
            fieldset=self.fieldset,
            name="Durability control",
            output_type="dict",
            creator=self.user,
        )
        self.extract = Extract.objects.create(
            corpus=self.corpus,
            fieldset=self.fieldset,
            name="Durability control",
            creator=self.user,
        )
        self.original = {
            "evidence": [{"quote": "Absent durability control wording.", "page": 1}]
        }
        self.cell = Datacell.objects.create(
            extract=self.extract,
            column=self.column,
            document=self.document,
            data=self.original,
            data_definition="dict",
            creator=self.user,
        )
        self.calls = []

    def tearDown(self):
        from opencontractserver.annotations.models import Annotation

        # These are this test's new rows, never the uploaded documents or findings.
        Annotation.objects.filter(corpus=self.corpus).delete()
        self.extract.delete()
        self.corpus.delete()
        self.fieldset.delete()

    def response(self, request, endpoint):
        self.calls.append(request)
        return {
            "http_status": 200,
            "request_id": "synthetic-control",
            "response": {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"quotations": [self.original_quote]})
                        },
                    }
                ]
            },
        }

    def assert_retained(self, state):
        self.cell.refresh_from_db()
        self.assertEqual(self.cell.data, self.original)
        attempts = list(self.cell.evidence_anchors["machineRepairs"].values())
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["state"], state)
        self.assertEqual(attempts[0]["attempt"], 1)
        return attempts[0]

    def test_one_invocation_reads_reuse_and_original_highlights_restore(self):
        from databricks_port.finding_evidence import finding_evidence
        from databricks_port.grounding import repair_machine_finding

        from opencontractserver.annotations.models import Annotation

        repair_machine_finding(self.cell, invoke_fn=self.response)
        first = finding_evidence(self.cell)
        self.assertEqual(first[0]["status"], "matched")
        identifiers = {q["annotationId"] for q in first}
        for _ in range(2):
            repair_machine_finding(self.cell, invoke_fn=self.response)
            self.assertEqual(
                {q["annotationId"] for q in finding_evidence(self.cell)}, identifiers
            )
        self.assertEqual(len(self.calls), 1)
        self.assert_retained("responded")
        self.assertIsNone(self.cell.corrected_data)
        self.cell.corrected_data = {
            "evidence": [{"quote": self.human_quote, "page": 1}]
        }
        self.cell.save(update_fields=["corrected_data"])
        corrected = finding_evidence(self.cell)
        self.assertTrue(
            all(q["status"] in {"matched", "different_page"} for q in corrected)
        )
        self.assertFalse(
            Annotation.objects.filter(
                pk__in=identifiers, data__quotationEvidence__active=True
            ).exists()
        )
        self.cell.corrected_data = None
        self.cell.save(update_fields=["corrected_data"])
        self.assertEqual(
            {q["annotationId"] for q in finding_evidence(self.cell)}, identifiers
        )
        self.assertTrue(
            Annotation.objects.filter(
                pk__in=identifiers, data__quotationEvidence__active=True
            ).exists()
        )
        self.assertEqual(len(self.calls), 1)

    def test_interrupted_admission_never_repeats_unknown_invocation(self):
        from databricks_port.finding_evidence import finding_evidence
        from databricks_port.grounding import repair_machine_finding

        def interrupted(request, endpoint):
            self.calls.append(request)
            raise KeyboardInterrupt("Control: process stops after durable admission")

        with self.assertRaises(KeyboardInterrupt):
            repair_machine_finding(self.cell, invoke_fn=interrupted)
        self.assert_retained("invoking")
        repair_machine_finding(self.cell, invoke_fn=self.response)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(finding_evidence(self.cell)[0]["status"], "unmatched")

    def test_saved_response_recovers_projection_without_inference(self):
        from databricks_port.finding_evidence import finding_evidence
        from databricks_port.grounding import repair_machine_finding

        with patch(
            "opencontractserver.extracts.services.quotation_grounding.quotations_from_response",
            side_effect=ValueError("Control: projection unavailable"),
        ):
            repair_machine_finding(self.cell, invoke_fn=self.response)
            self.assertEqual(finding_evidence(self.cell)[0]["status"], "unmatched")
        self.assertIn("response", self.assert_retained("responded"))
        self.assertEqual(finding_evidence(self.cell)[0]["status"], "matched")
        repair_machine_finding(self.cell, invoke_fn=self.response)
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_human_write_wins_over_late_provider_response(self):
        from databricks_port.finding_evidence import finding_evidence
        from databricks_port.grounding import repair_machine_finding
        from django.db import connections

        from opencontractserver.extracts.models import Datacell

        errors = []
        corrected = {"evidence": [{"quote": self.human_quote, "page": 1}]}

        def human_write():
            try:
                Datacell.objects.filter(pk=self.cell.pk).update(
                    corrected_data=corrected
                )
            except Exception as error:
                errors.append(error)
            finally:
                connections.close_all()

        def delayed(request, endpoint):
            worker = threading.Thread(target=human_write)
            worker.start()
            worker.join(timeout=45)
            self.assertFalse(
                worker.is_alive(),
                "Repair admission must release its DB lock before inference",
            )
            self.assertFalse(errors)
            return self.response(request, endpoint)

        repair_machine_finding(self.cell, invoke_fn=delayed)
        self.assert_retained("responded")
        self.assertEqual(self.cell.corrected_data, corrected)
        self.assertEqual(finding_evidence(self.cell)[0]["quote"], self.human_quote)
        repair_machine_finding(self.cell, invoke_fn=self.response)
        self.assertEqual(len(self.calls), 1)


@unittest.skipUnless(
    os.environ.get("OPENCONTRACTS_QA_CONTEXT"), "Explicit QA context required"
)
class FreshDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runpy.run_path(os.environ["OPENCONTRACTS_QA_CONTEXT"])

    def test_repeat_preserves_ids_and_refuses_native_edits(self):
        from pathlib import Path

        from databricks_port.definitions import install_definitions
        from django.db import transaction

        from opencontractserver.extracts.models import Column

        root = Path(os.environ["WORKFLOW_PACKAGE_ROOT"])
        for directory in root.iterdir():
            if not directory.is_dir():
                continue
            before = install_definitions(directory.name, "pilot-owner")
            self.assertEqual(before, install_definitions(directory.name, "pilot-owner"))
            with transaction.atomic():
                column = Column.objects.filter(
                    fieldset_id=before["fieldset_id"]
                ).first()
                column.query = "Native edited query must remain intact"
                column.save(update_fields=["query"])
                with self.assertRaisesRegex(ValueError, "definitions have changed"):
                    install_definitions(directory.name, "pilot-owner")
                column.refresh_from_db()
                self.assertEqual(column.query, "Native edited query must remain intact")
                transaction.set_rollback(True)

    def test_new_owner_defers_personal_corpus_until_upload(self):
        from django.contrib.auth import get_user_model
        from django.db import transaction

        from opencontractserver.corpuses.models import Corpus

        with transaction.atomic():
            user = get_user_model().objects.create(
                username="fresh-virgin-owner-control"
            )
            self.assertFalse(Corpus.objects.filter(creator=user).exists())
            personal = Corpus.get_or_create_personal_corpus(user)
            self.assertTrue(personal.is_personal)
            self.assertEqual(Corpus.objects.filter(creator=user).count(), 1)
            transaction.set_rollback(True)


if __name__ == "__main__":
    unittest.main()
