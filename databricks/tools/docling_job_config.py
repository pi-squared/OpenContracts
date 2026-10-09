"""Pinned, isolated serverless Docling job and Databricks App resource contract."""

DEPENDENCIES = [
    "docling-slim[standard,feat-ocr-rapidocr-onnx]==2.132.0",
    "opencv-python-headless==4.12.0.88",
]


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
