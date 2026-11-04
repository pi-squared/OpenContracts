"""Exercise the real library aggregate against isolated in-memory rows.

The visibility and search seams supply a local table; the resolver's actual
Count/Q expressions execute in SQLite. No application database is connected.
"""

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from django.db import connections, models

from config.graphql import document_queries


class TerminalCountRow(models.Model):
    objects: models.Manager["TerminalCountRow"] = models.Manager()
    backend_lock = models.BooleanField()
    processing_status = models.CharField(max_length=20)
    page_count = models.IntegerField(default=0)

    class Meta:
        app_label = "tests"


class DocumentFailureCountTests(unittest.TestCase):
    """Terminal failed rows must belong to neither progress tile."""

    alias = "terminal_failure_count_test"
    databases: set[str] = set()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connections.databases[cls.alias] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            "ATOMIC_REQUESTS": False,
            "AUTOCOMMIT": True,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "OPTIONS": {},
            "TIME_ZONE": None,
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
            "TEST": {},
        }
        with connections[cls.alias].schema_editor() as editor:
            editor.create_model(TerminalCountRow)

    @classmethod
    def tearDownClass(cls):
        connections[cls.alias].close()
        del connections[cls.alias]
        del connections.databases[cls.alias]
        super().tearDownClass()

    def setUp(self):
        self.rows = TerminalCountRow.objects.using(self.alias)
        self.rows.all().delete()

    def counts(self):
        visible = self.rows.all()
        resolver = inspect.unwrap(document_queries._resolve_Query_document_stats)
        with (
            patch.object(
                document_queries.BaseService, "filter_visible", return_value=visible
            ),
            patch.object(
                document_queries,
                "DocumentFilter",
                return_value=SimpleNamespace(qs=visible),
            ),
            patch.object(document_queries, "Document") as document_model,
        ):
            document_model.objects.filter.side_effect = self.rows.filter
            return resolver(
                None, SimpleNamespace(context=SimpleNamespace(user=object()))
            )

    def test_failed_rows_with_either_lock_are_not_processing_or_processed(self):
        for locked in (True, False):
            self.rows.create(
                backend_lock=locked, processing_status="failed", page_count=1
            )
        counts = self.counts()
        self.assertEqual(counts.total_docs, 2)
        self.assertEqual(counts.total_pages, 2)
        self.assertEqual(counts.processing_count, 0)
        self.assertEqual(counts.processed_count, 0)

    def test_active_completed_and_legacy_rows_keep_their_lock_counts(self):
        self.rows.create(
            backend_lock=True, processing_status="processing", page_count=2
        )
        self.rows.create(backend_lock=True, processing_status="pending", page_count=3)
        self.rows.create(
            backend_lock=False, processing_status="completed", page_count=4
        )
        self.rows.create(backend_lock=False, processing_status="pending", page_count=5)
        self.rows.create(backend_lock=False, processing_status="", page_count=6)
        counts = self.counts()
        self.assertEqual(counts.total_docs, 5)
        self.assertEqual(counts.total_pages, 20)
        self.assertEqual(counts.processing_count, 2)
        self.assertEqual(counts.processed_count, 3)
