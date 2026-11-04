"""Exercise the real library aggregate against isolated in-memory rows.

The visibility and search seams supply a local table; the resolver's actual
Count/Q expressions execute in SQLite. No application database is connected.
"""

import inspect
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import connections, models

from config.graphql import document_queries


class TerminalCountRow(models.Model):
    objects: models.Manager["TerminalCountRow"] = models.Manager()
    backend_lock = models.BooleanField()
    processing_status = models.CharField(max_length=20)
    page_count = models.IntegerField(default=0)

    class Meta:
        app_label = "tests"


@pytest.fixture
def isolated_rows(django_db_blocker) -> Iterator[models.QuerySet[TerminalCountRow]]:
    """Allow only the local SQL seam while retaining a default-DB tripwire."""
    alias = "terminal_failure_count_test"
    assert alias not in connections.databases
    connections.databases[alias] = {
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
    connection = connections[alias]
    try:
        with (
            django_db_blocker.unblock(),
            patch.object(
                connections["default"],
                "ensure_connection",
                side_effect=AssertionError("Count regression must use isolated SQLite"),
            ),
        ):
            with connection.schema_editor() as editor:
                editor.create_model(TerminalCountRow)
            yield TerminalCountRow.objects.using(alias)
    finally:
        connection.close()
        del connections[alias]
        del connections.databases[alias]


class TestDocumentFailureCounts:
    """Terminal failed rows must belong to neither progress tile."""

    def counts(self, rows):
        visible = rows.all()
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
            document_model.objects.filter.side_effect = rows.filter
            return resolver(
                None, SimpleNamespace(context=SimpleNamespace(user=object()))
            )

    def test_failed_rows_with_either_lock_are_not_processing_or_processed(
        self, isolated_rows
    ):
        for locked in (True, False):
            isolated_rows.create(
                backend_lock=locked, processing_status="failed", page_count=1
            )
        counts = self.counts(isolated_rows)
        assert counts.total_docs == 2
        assert counts.total_pages == 2
        assert counts.processing_count == 0
        assert counts.processed_count == 0

    def test_active_completed_and_legacy_rows_keep_their_lock_counts(
        self, isolated_rows
    ):
        isolated_rows.create(
            backend_lock=True, processing_status="processing", page_count=2
        )
        isolated_rows.create(
            backend_lock=True, processing_status="pending", page_count=3
        )
        isolated_rows.create(
            backend_lock=False, processing_status="completed", page_count=4
        )
        isolated_rows.create(
            backend_lock=False, processing_status="pending", page_count=5
        )
        isolated_rows.create(backend_lock=False, processing_status="", page_count=6)
        counts = self.counts(isolated_rows)
        assert counts.total_docs == 5
        assert counts.total_pages == 20
        assert counts.processing_count == 2
        assert counts.processed_count == 3
