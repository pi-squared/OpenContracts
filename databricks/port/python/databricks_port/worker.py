"""Bounded in-process Celery worker for native asynchronous pilot workflows."""

import os
import threading


def start(app=None):
    from celery.signals import worker_ready

    if app is None:
        from config.celery_app import app

        app.loader.import_default_modules()
    ready = threading.Event()

    def on_ready(sender, **kwargs):
        if sender.app is app:
            ready.set()

    worker_ready.connect(on_ready, weak=False)
    worker = app.Worker(
        pool="threads",
        concurrency=int(os.environ.get("OPENCONTRACTS_WORKER_CONCURRENCY", "2")),
        queues=[app.conf.task_default_queue, "doc_parse", "worker_uploads"],
        loglevel="INFO",
        without_mingle=True,
        without_gossip=True,
        without_heartbeat=True,
        redirect_stdouts=False,
    )
    thread = threading.Thread(
        target=worker.start, name="opencontracts-worker", daemon=True
    )
    thread.start()
    try:
        if not ready.wait(45):
            raise RuntimeError("Native background worker did not become ready")
    finally:
        worker_ready.disconnect(on_ready)
    return worker
