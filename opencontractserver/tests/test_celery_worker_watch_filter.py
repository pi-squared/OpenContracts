"""Generated local media must not restart a worker processing its ingest chain."""

import shlex
import unittest
from collections.abc import Callable
from pathlib import Path

from watchfiles import Change
from watchfiles.cli import build_filter

REPO_ROOT = Path(__file__).resolve().parents[2]


def worker_watch_filter() -> Callable[[Change, str], bool]:
    start = REPO_ROOT / "compose/local/django/celery/worker/start"
    command = next(
        line
        for line in start.read_text().splitlines()
        if line.startswith("watchfiles ")
    )
    arguments = shlex.split(command)
    ignored = arguments[arguments.index("--ignore-paths") + 1]
    # The entrypoint runs from /app, the repository root. Resolve the real
    # command's relative paths identically without changing the test cwd.
    paths = ",".join(str(REPO_ROOT / path) for path in ignored.split(","))
    watch_filter, _ = build_filter("default", paths)
    assert watch_filter is not None
    return watch_filter


class CeleryWorkerWatchFilterTests(unittest.TestCase):
    def test_generated_local_media_does_not_restart_worker(self) -> None:
        watch_filter = worker_watch_filter()
        # config/settings/base.py defines LOCAL MEDIA_ROOT as APPS_DIR / media,
        # inside opencontractserver, rather than the top-level /app/media.
        media_root = REPO_ROOT / "opencontractserver/media"
        for relative_path in (
            "documents/upload.pdf",
            "parses/document.json",
            "text/document.txt",
            "thumbnails/document.jpg",
        ):
            with self.subTest(relative_path=relative_path):
                self.assertFalse(
                    watch_filter(Change.added, str(media_root / relative_path))
                )

    def test_python_source_changes_still_restart_worker(self) -> None:
        self.assertTrue(
            worker_watch_filter()(
                Change.modified,
                str(REPO_ROOT / "opencontractserver/tasks/doc_tasks.py"),
            )
        )
