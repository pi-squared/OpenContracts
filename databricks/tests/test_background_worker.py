"""Exercise asynchronous Celery dispatch with a real isolated memory worker."""

import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))


class BackgroundWorkerTests(unittest.TestCase):
    def test_native_task_returns_before_execution_and_completes(self):
        from celery import Celery
        from databricks_port.worker import start

        app = Celery("worker-control", broker="memory://", backend="cache+memory://")
        app.conf.update(
            task_default_queue="control-" + uuid.uuid4().hex, task_always_eager=False
        )

        @app.task(name="worker-control.echo")
        def echo(value):
            time.sleep(0.5)
            return value

        worker = start(app=app)
        try:
            began = time.monotonic()
            result = echo.delay("native-background-control")
            self.assertLess(time.monotonic() - began, 0.5)
            self.assertEqual(
                result.get(timeout=15, disable_sync_subtasks=False),
                "native-background-control",
            )
        finally:
            worker.stop()


if __name__ == "__main__":
    unittest.main()
