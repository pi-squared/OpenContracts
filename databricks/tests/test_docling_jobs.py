"""Verify source identity, duplicate submission recovery and retained evidence."""

import copy
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "port/python"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from databricks_port.docling_jobs import (  # noqa: E402
    DoclingJobError,
    encoded,
    new_attempt,
    parse_job,
)
from docling_job_config import app_resources, job_settings  # noqa: E402


class Client:
    def __init__(self, attempt, export):
        self.files = self
        self.jobs = self
        self.uploads = {}
        self.submissions = []
        self.fail_response = False
        self.result_state = "SUCCESS"
        self.export = encoded(export)
        self.receipt = {
            "attempt_id": attempt["attempt_id"],
            "source_sha256": attempt["source_sha256"],
            "parser_version": "2.132.0",
            "options": attempt["options"],
            "status": "success",
            "export_sha256": hashlib.sha256(self.export).hexdigest(),
            "page_count": export["page_count"],
        }

    def create_directory(self, path):
        pass

    def upload(self, path, content, overwrite):
        from databricks.sdk.errors import ResourceAlreadyExists

        assert not overwrite
        if path in self.uploads:
            raise ResourceAlreadyExists()
        self.uploads[path] = content.read()

    def download(self, path):
        content = self.uploads.get(path)
        if content is None:
            content = (
                encoded(self.receipt) if path.endswith("receipt.json") else self.export
            )
        return SimpleNamespace(contents=io.BytesIO(content))

    def run_now(self, **request):
        self.submissions.append(request)
        if self.fail_response:
            self.fail_response = False
            raise ConnectionError("Submission response lost")
        return SimpleNamespace(run_id=123)

    def get_run(self, run_id):
        assert run_id == 123
        return SimpleNamespace(
            state=SimpleNamespace(
                as_dict=lambda: {
                    "life_cycle_state": "TERMINATED",
                    "result_state": self.result_state,
                }
            )
        )


class DoclingJobTests(unittest.TestCase):
    def setUp(self):
        self.source = b"original PDF bytes"
        self.attempt = new_attempt(
            self.source,
            42,
            "/Volumes/c/s/v",
            "Sample",
            {
                "do_ocr": True,
                "do_table_structure": True,
            },
        )
        # Retained paragraph geometry must survive the job bridge verbatim.
        self.export = {
            "page_count": 1,
            "content": "Actual text",
            "pawls_file_content": [
                {
                    "page": {"width": 100, "height": 200},
                    "tokens": [
                        {"x": 3, "y": 4, "width": 5, "height": 6, "text": "Actual text"}
                    ],
                }
            ],
        }
        self.client = Client(self.attempt, self.export)
        self.saved = []

    def persist(self, value):
        self.saved.append(copy.deepcopy(value))

    def parse(self):
        return parse_job(
            self.source, self.attempt, self.persist, self.client, poll_seconds=0
        )

    def test_request_is_retained_before_submission_and_geometry_is_preserved(self):
        original = self.client.run_now

        def submit(**kwargs):
            self.assertEqual(self.saved[-1]["state"], "submitting")
            request = self.saved[-1]["request"]
            self.assertEqual(self.client.uploads[request["source_path"]], self.source)
            return original(**kwargs)

        self.client.run_now = submit
        export, receipt = self.parse()
        self.assertEqual(export, self.export)
        self.assertEqual(
            receipt["source_sha256"], hashlib.sha256(self.source).hexdigest()
        )

    def test_lost_submission_reuses_same_token_and_import_retry_does_not_submit(self):
        self.client.fail_response = True
        with self.assertRaises(ConnectionError):
            self.parse()
        self.parse()
        self.assertEqual(self.client.submissions[0], self.client.submissions[1])
        self.parse()
        self.assertEqual(len(self.client.submissions), 2)

    def test_changed_source_never_submits(self):
        self.source = b"changed"
        with self.assertRaisesRegex(DoclingJobError, "Original PDF differs"):
            self.parse()
        self.assertEqual(self.client.submissions, [])

    def test_failed_job_is_retained_and_not_resubmitted(self):
        self.client.result_state = "FAILED"
        for _ in range(2):
            with self.assertRaisesRegex(DoclingJobError, "job failed"):
                self.parse()
        self.assertEqual(len(self.client.submissions), 1)
        self.assertEqual(self.saved[-1]["job_state"]["result_state"], "FAILED")

    def test_wrong_receipt_or_artifact_is_rejected(self):
        self.client.receipt["attempt_id"] = "different"
        with self.assertRaisesRegex(DoclingJobError, "identity differs"):
            self.parse()
        self.client.receipt["attempt_id"] = self.attempt["attempt_id"]
        self.client.export = b"{}"
        with self.assertRaisesRegex(DoclingJobError, "checksum differs"):
            self.parse()

    def test_serverless_job_has_no_automatic_parser_retry_and_resources_are_scoped(
        self,
    ):
        config = job_settings("fresh", "/Workspace/owned/revision", "principal")
        self.assertEqual(config["environments"][0]["spec"]["environment_version"], "6")
        self.assertEqual(config["tasks"][0]["max_retries"], 0)
        self.assertTrue(config["tasks"][0]["disable_auto_optimization"])
        self.assertEqual(config["run_as"]["service_principal_name"], "principal")
        resources = app_resources(42, "catalog.schema.artifacts")
        self.assertEqual(resources[0]["job"]["permission"], "CAN_MANAGE_RUN")
        self.assertEqual(
            {r["uc_securable"]["permission"] for r in resources[1:]},
            {"READ_VOLUME", "WRITE_VOLUME"},
        )

    def test_spark_kernel_without_file_launches_explicit_worker(self):
        source = Path(__file__).resolve().parents[1] / "jobs/docling_pdf_job.py"
        spec = importlib.util.spec_from_file_location("docling_worker_control", source)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        del worker.__file__
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "attempts" / self.attempt["attempt_id"]
            directory.mkdir(parents=True)
            manifest = directory / "request.json"
            with patch.object(
                sys,
                "argv",
                ["ipython", "--manifest", str(manifest), "--worker-file", str(source)],
            ), patch.object(
                worker, "request", return_value=({}, directory)
            ), patch.object(
                worker.subprocess, "run", return_value=SimpleNamespace(returncode=0)
            ) as process:
                worker.main()
            self.assertEqual(process.call_args.args[0][3], str(source))


if __name__ == "__main__":
    unittest.main()
