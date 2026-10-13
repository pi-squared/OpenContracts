"""Pinned, isolated serverless Docling job and Databricks App resource contract."""

import json

DEPENDENCIES = [
    "docling-slim[standard,feat-ocr-rapidocr-onnx]==2.132.0",
    "opencv-python-headless==4.12.0.88",
]

TASK_READBACK_DEFAULTS = {
    "disabled": False,
    "email_notifications": {},
    "min_retry_interval_millis": 0,
    "retry_on_timeout": False,
    "run_if": "ALL_SUCCESS",
    "timeout_seconds": 0,
}
JOB_READBACK_DEFAULTS = {
    "email_notifications": {},
    "webhook_notifications": {},
    "format": "MULTI_TASK",
}


def _without_omitted_defaults(requested, actual, defaults):
    normalized = dict(actual)
    for name, default in defaults.items():
        if (
            name not in requested
            and type(normalized.get(name)) is type(default)
            and normalized.get(name) == default
        ):
            del normalized[name]
    return normalized


def job_settings_match(expected, observed):
    """Compare complete settings, admitting only exact omitted server defaults."""
    requested_tasks = expected.get("tasks")
    observed_tasks = observed.get("tasks")
    if not isinstance(requested_tasks, list) or not isinstance(observed_tasks, list):
        return False
    if len(requested_tasks) != len(observed_tasks):
        return False
    tasks = []
    for requested, actual in zip(requested_tasks, observed_tasks):
        if not isinstance(requested, dict) or not isinstance(actual, dict):
            return False
        tasks.append(
            _without_omitted_defaults(requested, actual, TASK_READBACK_DEFAULTS)
        )
    selected = _without_omitted_defaults(expected, observed, JOB_READBACK_DEFAULTS)
    selected["tasks"] = tasks
    return json.dumps(selected, sort_keys=True, allow_nan=False) == json.dumps(
        expected, sort_keys=True, allow_nan=False
    )


def job_settings(app_name, workspace_directory, principal, rapidocr_wheel):
    return {
        "name": app_name + "-docling-pdf",
        "description": "Source-bound PDF parsing for " + app_name,
        "max_concurrent_runs": 4,
        "queue": {"enabled": True},
        "timeout_seconds": 3600,
        "performance_target": "PERFORMANCE_OPTIMIZED",
        "run_as": {"service_principal_name": principal},
        "tags": {
            "aidevkit_project": "ai-dev-kit",
            "app": app_name,
            "parser": "docling",
        },
        "parameters": [{"name": "manifest", "default": ""}],
        "environments": [
            {
                "environment_key": "docling",
                "spec": {
                    "environment_version": "6",
                    "dependencies": [*DEPENDENCIES, rapidocr_wheel],
                },
            }
        ],
        "tasks": [
            {
                "task_key": "parse_pdf",
                "environment_key": "docling",
                "max_retries": 0,
                "disable_auto_optimization": True,
                "spark_python_task": {
                    "python_file": workspace_directory + "/docling_pdf_job.py",
                    "source": "WORKSPACE",
                    "parameters": [
                        "--manifest",
                        "{{job.parameters.manifest}}",
                        "--worker-file",
                        workspace_directory + "/docling_pdf_job.py",
                    ],
                },
            }
        ],
    }


def app_resources(job_id, volume):
    return [
        {
            "name": "docling-job",
            "job": {"id": str(job_id), "permission": "CAN_MANAGE_RUN"},
        },
        {
            "name": "docling-artifacts",
            "uc_securable": {
                "securable_full_name": volume,
                "securable_type": "VOLUME",
                "permission": "WRITE_VOLUME",
            },
        },
        {
            "name": "docling-artifacts-read",
            "uc_securable": {
                "securable_full_name": volume,
                "securable_type": "VOLUME",
                "permission": "READ_VOLUME",
            },
        },
    ]
