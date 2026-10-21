"""Native retained-cache and annotation-feed checks (isolated PostgreSQL only)."""

from copy import deepcopy

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.annotations.services.evidence_visibility import (
    filter_finding_annotations,
    fingerprint,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.extracts.services.quotation_evidence import (
    finding_evidence,
    finding_identity,
    finding_sources,
)

QUOTE = "Where requested, notify the Owner of the whereabouts of the Goods."


class NotFoundEvidenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="evidence-reviewer")
        self.corpus = Corpus.objects.create(
            title="Retained findings", creator=self.user
        )
        self.document = Document.objects.create(
            title="Hire Purchase", creator=self.user
        )
        fieldset = Fieldset.objects.create(name="Terms", creator=self.user)
        self.column = Column.objects.create(
            fieldset=fieldset,
            creator=self.user,
            name="Tracking devices",
            output_type="dict",
        )
        self.extract = Extract.objects.create(
            corpus=self.corpus, fieldset=fieldset, creator=self.user
        )
        self.value = {
            "finding": "supported",
            "rationale": "Retained rationale",
            "evidence": [{"quote": QUOTE, "page": 3}],
        }
        self.cell = Datacell.objects.create(
            extract=self.extract,
            document=self.document,
            column=self.column,
            creator=self.user,
            data={"data": self.value},
            data_definition="dict",
            corrected_data={**self.value, "finding": "not_found"},
            approved_by=self.user,
            llm_call_log="Retained original call history",
        )
        label = AnnotationLabel.objects.create(
            text="Tracking devices", creator=self.user, label_type=TOKEN_LABEL
        )
        self.annotation = Annotation.objects.create(
            creator=self.user,
            document=self.document,
            corpus=self.corpus,
            annotation_label=label,
            annotation_type=TOKEN_LABEL,
            raw_text=QUOTE,
            page=3,
            json={},
            data={
                "domainEvidence": {
                    "managed": True,
                    "active": True,
                    "associations": [
                        {
                            "active": True,
                            "kind": "quote",
                            "datacellId": self.cell.pk,
                            "findingVersion": "original",
                            "findingFingerprint": fingerprint(self.value),
                            "selection": {
                                "selectionPath": "/evidence/0",
                                "quote": QUOTE,
                            },
                        }
                    ],
                }
            },
        )
        # Document creation signals may update source identity in the database.
        # Cache the persisted identity, just as the native resolver does.
        self.cell = Datacell.objects.select_related("document", "extract__corpus").get(
            pk=self.cell.pk
        )
        _, _, source, identity = finding_identity(self.cell, "original")
        self.cell.evidence_anchors = {
            "original": {
                "fingerprint": identity,
                "source": source,
                "quotes": [
                    {
                        "quote": QUOTE,
                        "reportedPage": 3,
                        "locatedPage": 4,
                        "status": "different_page",
                        "selectionPath": "/evidence/0",
                        "annotationId": self.annotation.pk,
                    }
                ],
            }
        }
        self.cell.save(update_fields=["evidence_anchors"])
        self.cell.sources.add(self.annotation)

    def test_effective_suppression_and_explicit_original_preserve_history(self):
        before = deepcopy(Datacell.objects.filter(pk=self.cell.pk).values().get())
        annotation_before = deepcopy(self.annotation.data)
        self.assertEqual(finding_evidence(self.cell), [])
        self.assertEqual(list(finding_sources(self.cell)), [])
        self.assertEqual(finding_evidence(self.cell, "original")[0]["quote"], QUOTE)
        self.assertEqual(
            [a.pk for a in finding_sources(self.cell, "original")], [self.annotation.pk]
        )
        self.assertEqual(
            Datacell.objects.filter(pk=self.cell.pk).values().get(), before
        )
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.data, annotation_before)
        self.assertEqual(list(self.cell.sources.all()), [self.annotation])

    def test_stale_active_feed_is_filtered_and_shared_passage_survives(self):
        feed = Annotation.objects.filter(document=self.document)
        self.assertFalse(filter_finding_annotations(feed).exists())
        positive = Datacell.objects.create(
            extract=self.extract,
            document=self.document,
            column=self.column,
            creator=self.user,
            data={"data": {**self.value, "finding": "contradicted"}},
            data_definition="dict",
        )
        domain = self.annotation.data["domainEvidence"]
        domain["associations"].append(
            {
                "active": True,
                "kind": "quote",
                "datacellId": positive.pk,
                "findingVersion": "original",
                "selection": {
                    "selectionPath": "/evidence/0",
                    "quote": QUOTE,
                },
            }
        )
        self.annotation.save(update_fields=["data"])
        # One metadata query and one batched cell query, regardless of association count.
        with self.assertNumQueries(3):
            visible = list(filter_finding_annotations(feed))
        self.assertEqual([a.pk for a in visible], [self.annotation.pk])
        self.assertTrue(visible[0]._eligible_evidence_quote)
        self.assertEqual(
            [
                item["datacellId"]
                for item in visible[0]._projected_domain_provenance["associations"]
            ],
            [positive.pk],
        )

    def test_graphql_version_arguments_and_old_annotation_link(self):
        from django.test import RequestFactory

        from config.graphql.schema import schema
        from opencontractserver.utils.ids import to_global_id

        # Exercise the real schema and node permission path, without a model call.
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        request = RequestFactory().post("/graphql/")
        request.user = self.user
        before = deepcopy(Datacell.objects.filter(pk=self.cell.pk).values().get())
        result = schema.execute_sync(
            """
            query Evidence($cell: ID!, $annotation: ID!) {
                datacell(id: $cell) {
                    current: findingEvidence
                    currentSources: fullSourceList { id }
                    original: findingEvidence(version: "original")
                    originalSources: fullSourceList(version: "original") { id isEvidenceQuote }
                }
                annotation(id: $annotation) { id }
            }
        """,
            variable_values={
                "cell": to_global_id("DatacellType", self.cell.pk),
                "annotation": to_global_id("AnnotationType", self.annotation.pk),
            },
            context_value=request,
        )
        self.assertIsNone(result.errors, result.errors)
        assert result.data is not None
        cell = result.data["datacell"]
        self.assertEqual(cell["current"], [])
        self.assertEqual(cell["currentSources"], [])
        self.assertEqual(cell["original"][0]["quote"], QUOTE)
        self.assertTrue(cell["originalSources"][0]["isEvidenceQuote"])
        self.assertIsNone(result.data["annotation"])
        self.assertEqual(
            Datacell.objects.filter(pk=self.cell.pk).values().get(), before
        )
