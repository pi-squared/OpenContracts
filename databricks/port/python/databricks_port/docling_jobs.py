"""Source-bound Docling job submission and immutable result retrieval."""

import hashlib
import io
import json
import re
import time
import uuid
from datetime import datetime, timezone

PARSER_PATH = "opencontractserver.pipeline.parsers.docling_job_parser.DoclingJobParser"
VERSION = "2.132.0"


class DoclingJobError(ValueError):
    """A safe failure message; detailed job diagnostics stay in private storage."""


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def volume_root(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"/Volumes/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*",
        value,
    ):
        raise DoclingJobError("Configure a safe Unity Catalog artifact volume path")
    return value.rstrip("/")


def new_attempt(source, job_id, root, title, options):
    root = volume_root(root)
    attempt_id = uuid.uuid4().hex
    return {
        "attempt_id": attempt_id,
        "job_id": int(job_id),
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "title": title,
        "options": options,
        "directory": root + "/attempts/" + attempt_id,
        "idempotency_token": "docling-" + attempt_id,
        "created_at": timestamp(),
        "state": "admitted",
    }


def download(client, path):
    response = client.files.download(path)
    try:
        content = response.contents.read(256 * 1024 * 1024 + 1)
    finally:
        response.contents.close()
    if len(content) > 256 * 1024 * 1024:
        raise DoclingJobError("Docling output exceeds the supported artifact size")
    return content


def immutable_upload(client, path, content):
    from databricks.sdk.errors import ResourceAlreadyExists

    try:
        client.files.upload(path, io.BytesIO(content), overwrite=False)
    except ResourceAlreadyExists:
        if download(client, path) != content:
            raise DoclingJobError("Retained Docling attempt input changed") from None


def parse_job(source, attempt, persist, client, *, timeout=3600, poll_seconds=5):
    """Reuse an admitted attempt; never create another run on status/import retry."""
    if hashlib.sha256(source).hexdigest() != attempt["source_sha256"]:
        raise DoclingJobError("Original PDF differs from the admitted Docling source")
    directory = volume_root(attempt["directory"])
    if not re.fullmatch(
        r"[0-9a-f]{32}", attempt["attempt_id"]
    ) or not directory.endswith("/attempts/" + attempt["attempt_id"]):
        raise DoclingJobError("Retained Docling attempt identity is invalid")
    manifest = {
        "attempt_id": attempt["attempt_id"],
        "source_sha256": attempt["source_sha256"],
        "source_path": directory + "/source.pdf",
        "output_directory": directory + "/result",
        "title": attempt["title"],
        "options": attempt["options"],
    }
    if not attempt.get("run_id"):
        client.files.create_directory(directory)
        immutable_upload(client, manifest["source_path"], source)
        immutable_upload(client, directory + "/request.json", encoded(manifest))
        # Admission is already durable. Persist the effective request before
        # run_now; replaying this exact token recovers a lost submission response.
        attempt.update(state="submitting", request=manifest)
        persist(attempt)
        run = client.jobs.run_now(
            job_id=attempt["job_id"],
            idempotency_token=attempt["idempotency_token"],
            job_parameters={"manifest": directory + "/request.json"},
        )
        attempt.update(run_id=run.run_id, state="submitted", submitted_at=timestamp())
        persist(attempt)
    deadline = time.monotonic() + timeout
    while True:
        run = client.jobs.get_run(run_id=attempt["run_id"])
        state = run.state.as_dict() if run.state else {}
        lifecycle = state.get("life_cycle_state")
        if lifecycle in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
            attempt.update(state="terminal", job_state=state, finished_at=timestamp())
            persist(attempt)
            if state.get("result_state") != "SUCCESS":
                raise DoclingJobError(
                    "Docling Databricks job failed; run " + str(attempt["run_id"])
                )
            break
        if time.monotonic() >= deadline:
            raise DoclingJobError(
                "Docling job is still pending; recover the retained run "
                + str(attempt["run_id"])
            )
        time.sleep(poll_seconds)
    receipt = json.loads(download(client, directory + "/result/receipt.json"))
    if (
        receipt.get("attempt_id") != attempt["attempt_id"]
        or receipt.get("source_sha256") != attempt["source_sha256"]
        or receipt.get("parser_version") != VERSION
        or receipt.get("options") != attempt["options"]
        or receipt.get("status") != "success"
    ):
        raise DoclingJobError(
            "Docling result identity differs from its admitted source"
        )
    content = download(client, directory + "/result/export.json")
    if hashlib.sha256(content).hexdigest() != receipt["export_sha256"]:
        raise DoclingJobError("Retained Docling result checksum differs")
    export = json.loads(content)
    if export["page_count"] != receipt["page_count"]:
        raise DoclingJobError("Docling result page coverage differs from its receipt")
    attempt.update(state="retrieved", receipt=receipt)
    persist(attempt)
    return export, receipt
