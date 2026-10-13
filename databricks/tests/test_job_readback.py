"""Owned job readback admits only the server's exact omitted task defaults."""

import copy
import unittest

from tools.docling_job_config import job_settings_match


class JobReadbackTests(unittest.TestCase):
    def setUp(self):
        self.expected = {
            "name": "source-bound-parser",
            "run_as": {"service_principal_name": "configured-principal"},
            "parameters": [{"name": "manifest", "default": ""}],
            "environments": [
                {
                    "environment_key": "parser",
                    "spec": {
                        "environment_version": "6",
                        "dependencies": ["retained-wheel"],
                    },
                }
            ],
            "tasks": [
                {
                    "task_key": "first",
                    "environment_key": "parser",
                    "max_retries": 0,
                    "spark_python_task": {
                        "python_file": "/Workspace/fixture/first.py",
                        "source": "WORKSPACE",
                        "parameters": ["--manifest", "{{job.parameters.manifest}}"],
                    },
                },
                {
                    "task_key": "second",
                    "depends_on": [{"task_key": "first"}],
                    "environment_key": "parser",
                    "spark_python_task": {
                        "python_file": "/Workspace/fixture/second.py",
                        "source": "WORKSPACE",
                    },
                },
            ],
        }
        self.observed = copy.deepcopy(self.expected)
        for task in self.observed["tasks"]:
            task.update(
                disabled=False,
                email_notifications={},
                min_retry_interval_millis=0,
                retry_on_timeout=False,
                run_if="ALL_SUCCESS",
                timeout_seconds=0,
            )

    def test_numeric_false_alias_is_not_an_exact_disabled_default(self):
        self.observed["tasks"][0]["disabled"] = 0
        self.assertFalse(job_settings_match(self.expected, self.observed))

    def test_exact_server_defaults_match_without_changing_either_declaration(self):
        self.observed.update(
            email_notifications={}, webhook_notifications={}, format="MULTI_TASK"
        )
        expected_before = copy.deepcopy(self.expected)
        observed_before = copy.deepcopy(self.observed)
        self.assertTrue(job_settings_match(self.expected, self.observed))
        self.assertEqual(self.expected, expected_before)
        self.assertEqual(self.observed, observed_before)

    def test_nondefault_or_wrongly_typed_task_defaults_are_rejected(self):
        for name, value in (
            ("disabled", True),
            ("email_notifications", {"on_failure": ["operator@example.invalid"]}),
            ("min_retry_interval_millis", 100),
            ("retry_on_timeout", True),
            ("run_if", "ALL_DONE"),
            ("timeout_seconds", 60),
            ("email_notifications", []),
            ("min_retry_interval_millis", False),
            ("min_retry_interval_millis", 0.0),
            ("retry_on_timeout", 0),
            ("timeout_seconds", False),
        ):
            with self.subTest(field=name, value=value):
                observed = copy.deepcopy(self.observed)
                observed["tasks"][0][name] = value
                self.assertFalse(job_settings_match(self.expected, observed))

    def test_nondefault_or_wrongly_typed_job_defaults_are_rejected(self):
        for name, value in (
            ("email_notifications", {"on_failure": ["operator@example.invalid"]}),
            ("webhook_notifications", {"on_failure": [{"id": "changed-hook"}]}),
            ("format", "SINGLE_TASK"),
            ("email_notifications", []),
            ("webhook_notifications", []),
            ("format", None),
        ):
            with self.subTest(field=name, value=value):
                observed = copy.deepcopy(self.observed)
                observed[name] = value
                self.assertFalse(job_settings_match(self.expected, observed))

    def test_unknown_task_and_job_settings_are_rejected(self):
        for name, value in (
            ("schedule", {"quartz_cron_expression": "0 0 * * * ?"}),
            ("trigger", {"periodic": {"interval": 1, "unit": "HOURS"}}),
            ("continuous", {"pause_status": "UNPAUSED"}),
            ("job_clusters", [{"job_cluster_key": "unexpected"}]),
        ):
            with self.subTest(job_field=name):
                observed = copy.deepcopy(self.observed)
                observed[name] = value
                self.assertFalse(job_settings_match(self.expected, observed))
        for name, value in (
            ("health", {"rules": []}),
            ("existing_cluster_id", "unexpected-cluster"),
            ("notebook_task", {"notebook_path": "/Workspace/other"}),
        ):
            with self.subTest(task_field=name):
                observed = copy.deepcopy(self.observed)
                observed["tasks"][0][name] = value
                self.assertFalse(job_settings_match(self.expected, observed))

    def test_explicitly_requested_defaults_are_never_omitted_or_overridden(self):
        for task_level, name, requested in (
            (True, "timeout_seconds", 300),
            (True, "disabled", True),
            (True, "run_if", "ALL_DONE"),
            (False, "format", "SINGLE_TASK"),
            (False, "email_notifications", {"on_failure": ["owner@example.invalid"]}),
        ):
            with self.subTest(task_level=task_level, field=name):
                expected = copy.deepcopy(self.expected)
                observed = copy.deepcopy(self.observed)
                requested_fields = expected["tasks"][0] if task_level else expected
                actual_fields = observed["tasks"][0] if task_level else observed
                requested_fields[name] = requested
                self.assertFalse(job_settings_match(expected, observed))
                actual_fields[name] = requested
                self.assertTrue(job_settings_match(expected, observed))
                del actual_fields[name]
                self.assertFalse(job_settings_match(expected, observed))

    def test_requested_nested_settings_and_execution_identity_remain_exact(self):
        for path, value in (
            (("run_as", "service_principal_name"), "another-principal"),
            (("environments", 0, "spec", "environment_version"), "7"),
            (("environments", 0, "spec", "dependencies"), ["other-wheel"]),
            (("parameters", 0, "default"), "unexpected-manifest"),
            (("tasks", 0, "spark_python_task", "python_file"), "/Workspace/other.py"),
            (("tasks", 0, "spark_python_task", "source"), "GIT"),
            (("tasks", 0, "spark_python_task", "parameters"), []),
            (("tasks", 0, "max_retries"), False),
            (("tasks", 1, "depends_on"), []),
            (("tasks", 1, "task_key"), "other-task"),
        ):
            with self.subTest(path=path):
                observed = copy.deepcopy(self.observed)
                fields = observed
                for segment in path[:-1]:
                    fields = fields[segment]
                fields[path[-1]] = value
                self.assertFalse(job_settings_match(self.expected, observed))

    def test_missing_extra_reordered_and_malformed_tasks_are_rejected(self):
        tasks = self.observed["tasks"]
        for changed in (
            tasks[:-1],
            [*tasks, copy.deepcopy(tasks[0])],
            list(reversed(tasks)),
            None,
            {},
            [None, tasks[1]],
        ):
            with self.subTest(tasks=changed):
                observed = copy.deepcopy(self.observed)
                observed["tasks"] = changed
                self.assertFalse(job_settings_match(self.expected, observed))
