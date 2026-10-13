"""The build controller promotes gated bytes through its public Git command."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools import deploy_installation as deployment
from tools.verify_staged_runtime import (
    CONTROL,
    SOURCE_FILES,
    inventory,
    source_identity,
)

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "tools/build_release.py"


class ReleasePromotionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "development"
        self.destination = self.root / "testing"
        self.remote = self.root / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        for directory in (self.source, self.destination):
            directory.mkdir()
            self.git(directory, "init", "-q")
            self.git(directory, "config", "user.name", "Fixture")
            self.git(directory, "config", "user.email", "fixture@example.invalid")
        (self.source / "databricks").mkdir()
        for name in SOURCE_FILES:
            target = self.source / "databricks" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        for entry in json.loads((ROOT / "upstream.lock.json").read_text())["patches"]:
            target = self.source / "databricks" / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / entry["path"], target)
        (self.source / "databricks/upstream.lock.json").write_bytes(
            (ROOT / "upstream.lock.json").read_bytes()
        )
        (self.source / "databricks/README.md").write_text(
            "Maintained development recipe\n"
        )
        self.git(self.source, "add", "--", "databricks")
        self.git(self.source, "commit", "-qm", "Development fixture")
        self.source_commit = self.git(self.source, "rev-parse", "HEAD")
        (self.destination / "stock.txt").write_text("Unchanged stock application\n")
        self.git(self.destination, "add", "--", "stock.txt")
        self.git(self.destination, "commit", "-qm", "Stock fixture")
        self.git(self.destination, "checkout", "-qb", "testing/databricks-port")
        self.git(
            self.destination,
            "remote",
            "add",
            "origin",
            "https://github.com/pi-squared/OpenContracts.git",
        )
        self.git(
            self.destination,
            "config",
            "url." + str(self.remote) + ".insteadOf",
            "https://github.com/pi-squared/OpenContracts.git",
        )
        self.release = self.root / "release"
        self.release.mkdir()
        (self.release / "app.py").write_text("print('self-contained runtime')\n")
        (self.release / "release.json").write_text(
            json.dumps(
                {
                    "lock_sha256": hashlib.sha256(
                        (ROOT / "upstream.lock.json").read_bytes()
                    ).hexdigest(),
                    "archive_sha256": "a" * 64,
                }
            )
        )
        (self.release / "app.yaml").write_text(
            "command: [python, app.py]\nenv:\n  - name: INSTALLATION_CONFIG_JSON\n    valueFrom: installation-config\n"
        )
        self.gate = self.root / "gate.json"
        self.gate.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "passed": True,
                    "reason": "verified",
                    "executed": 1,
                    "skipped": 0,
                    "checks": {
                        "staged_launcher": {
                            "test_ids": [CONTROL],
                            "executed": 1,
                            "skipped": 0,
                            "failures": 0,
                            "errors": 0,
                            "successful": True,
                        },
                        "isolated_archive_imports": {
                            "imports": [
                                "databricks_port.warp_pdf",
                                "databricks_port.parser_exports",
                            ]
                        },
                    },
                    "release_directory": str(self.release),
                    "source_directory": str(self.source / "databricks"),
                    "python": {"executable": sys.executable},
                    "staged_files": inventory(self.release),
                    "source_files": source_identity(),
                }
            )
        )
        self.plan = self.root / "plan.json"

    @staticmethod
    def git(directory, *args):
        return subprocess.check_output(
            ["git", "-C", str(directory), *args], text=True, stderr=subprocess.PIPE
        ).strip()

    def plan_promotion(self):
        return subprocess.run(
            [
                sys.executable,
                str(COMMAND),
                "plan-promotion",
                "--development-checkout",
                str(self.source),
                "--development-commit",
                self.source_commit,
                "--destination-checkout",
                str(self.destination),
                "--testing-branch",
                "testing/databricks-port",
                "--release",
                str(self.release),
                "--receipt",
                str(self.gate),
                "--runtime-python",
                sys.executable,
                "--output",
                str(self.plan),
            ],
            capture_output=True,
            text=True,
        )

    def promote(self, name):
        return subprocess.run(
            [
                sys.executable,
                str(COMMAND),
                "promote",
                "--plan",
                str(self.plan),
                "--output",
                str(self.root / (name + ".json")),
            ],
            capture_output=True,
            text=True,
        )

    def test_promoted_runtime_is_exact_and_repeat_publication_keeps_the_same_commit(
        self,
    ):
        planned = self.plan_promotion()
        self.assertEqual(planned.returncode, 0, planned.stderr)
        result = self.promote("published")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.destination / "databricks/app/app.py").read_bytes(),
            (self.release / "app.py").read_bytes(),
        )
        self.assertEqual(
            (self.destination / "stock.txt").read_text(),
            "Unchanged stock application\n",
        )
        first = self.git(self.destination, "rev-parse", "HEAD")
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ).split()[0],
            first,
        )
        self.assertEqual(self.promote("repeated").returncode, 0)
        self.assertEqual(self.git(self.destination, "rev-parse", "HEAD"), first)

    def test_changed_release_stops_before_a_testing_commit_or_push(self):
        self.assertEqual(self.plan_promotion().returncode, 0)
        before = self.git(self.destination, "rev-parse", "HEAD")
        (self.release / "app.py").write_text("print('changed after gate')\n")
        result = self.promote("changed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Release or gate changed", result.stderr)
        self.assertEqual(self.git(self.destination, "rev-parse", "HEAD"), before)
        self.assertFalse((self.destination / "databricks/app").exists())
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ),
            "",
        )

    def test_hash_pinned_patch_blank_context_prefixes_are_published_byte_exact(self):
        patch_path = "databricks/patches/0055-shared-extract-outcome-notice.patch"
        expected = (
            ROOT / "patches/0055-shared-extract-outcome-notice.patch"
        ).read_bytes()
        self.assertIn(b"\n \n", expected)
        planned = self.plan_promotion()
        self.assertEqual(planned.returncode, 0, planned.stderr)
        result = self.promote("patch-context")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.destination / patch_path).read_bytes(), expected)
        published = json.loads((self.root / "patch-context.json").read_text())
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ).split()[0],
            published["head"],
        )
        repeated = self.promote("patch-context-repeated")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(
            json.loads((self.root / "patch-context-repeated.json").read_text())["head"],
            published["head"],
        )

    def commit_fixture_source(self):
        self.git(self.source, "add", "--", "databricks")
        self.git(self.source, "commit", "-qm", "Changed maintained source fixture")
        self.source_commit = self.git(self.source, "rev-parse", "HEAD")
        manifest = json.loads((self.release / "release.json").read_text())
        manifest["lock_sha256"] = hashlib.sha256(
            (self.source / "databricks/upstream.lock.json").read_bytes()
        ).hexdigest()
        (self.release / "release.json").write_text(json.dumps(manifest))
        gate = json.loads(self.gate.read_text())
        gate.update(
            staged_files=inventory(self.release),
            source_files=source_identity(self.source / "databricks"),
        )
        self.gate.write_text(json.dumps(gate))

    def assert_whitespace_stops_publication(self, expected_error):
        planned = self.plan_promotion()
        self.assertEqual(planned.returncode, 0, planned.stderr)
        before = self.git(self.destination, "rev-parse", "HEAD")
        result = self.promote("invalid-whitespace")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected_error, result.stderr)
        self.assertEqual(self.git(self.destination, "rev-parse", "HEAD"), before)
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ),
            "",
        )
        self.assertFalse((self.root / "invalid-whitespace.json").exists())

    def test_ordinary_source_trailing_whitespace_still_blocks_publication(self):
        (self.source / "databricks/README.md").write_text(
            "ordinary source has trailing whitespace  \n"
        )
        self.commit_fixture_source()
        self.assert_whitespace_stops_publication("returned non-zero exit status 2")

    def test_undeclared_patch_context_whitespace_has_no_exception(self):
        patch_path = self.source / "databricks/patches/undeclared.patch"
        patch_path.write_text(
            "--- a/example.txt\n+++ b/example.txt\n@@ -1,2 +1,2 @@\n \n-old\n+new\n"
        )
        self.commit_fixture_source()
        self.assert_whitespace_stops_publication("returned non-zero exit status 2")

    def test_pinned_patch_added_line_whitespace_is_rejected(self):
        patch_path = (
            self.source / "databricks/patches/0055-shared-extract-outcome-notice.patch"
        )
        content = patch_path.read_text().replace(
            "+import { ExtractOutcomeNotice }", "+import  { ExtractOutcomeNotice }", 1
        )
        lines = content.splitlines()
        index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith("+import  { ExtractOutcomeNotice }")
        )
        lines[index] += "  "
        patch_path.write_text("\n".join(lines) + "\n")
        lock_path = self.source / "databricks/upstream.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["patches"][-1]["sha256"] = hashlib.sha256(
            patch_path.read_bytes()
        ).hexdigest()
        lock_path.write_text(json.dumps(lock))
        self.commit_fixture_source()
        self.assert_whitespace_stops_publication(
            "Pinned patch contains invalid trailing whitespace"
        )

    def test_pinned_patch_blank_prefix_outside_a_hunk_is_rejected(self):
        patch_path = (
            self.source / "databricks/patches/0055-shared-extract-outcome-notice.patch"
        )
        with patch_path.open("a") as stream:
            stream.write(" \n")
        lock_path = self.source / "databricks/upstream.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["patches"][-1]["sha256"] = hashlib.sha256(
            patch_path.read_bytes()
        ).hexdigest()
        lock_path.write_text(json.dumps(lock))
        self.commit_fixture_source()
        self.assert_whitespace_stops_publication(
            "Pinned patch contains invalid trailing whitespace"
        )

    def test_pinned_patch_extra_blank_line_at_eof_is_rejected(self):
        patch_path = (
            self.source / "databricks/patches/0055-shared-extract-outcome-notice.patch"
        )
        with patch_path.open("a") as stream:
            stream.write("\n")
        lock_path = self.source / "databricks/upstream.lock.json"
        lock = json.loads(lock_path.read_text())
        lock["patches"][-1]["sha256"] = hashlib.sha256(
            patch_path.read_bytes()
        ).hexdigest()
        lock_path.write_text(json.dumps(lock))
        self.commit_fixture_source()
        self.assert_whitespace_stops_publication("returned non-zero exit status 2")

    def test_repeat_plan_rejects_a_committed_and_pushed_recipe_change(self):
        self.assertEqual(self.plan_promotion().returncode, 0)
        self.assertEqual(self.promote("published").returncode, 0)
        (self.destination / "databricks/upstream.lock.json").write_text("{}\n")
        self.git(self.destination, "add", "--", "databricks/upstream.lock.json")
        self.git(self.destination, "commit", "-qm", "Changed recipe after promotion")
        self.git(self.destination, "push", "-q", "origin", "HEAD")
        changed = self.git(self.destination, "rev-parse", "HEAD")
        result = self.promote("stale-repeat")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Previously promoted source changed", result.stderr)
        self.assertEqual(self.git(self.destination, "rev-parse", "HEAD"), changed)
        self.assertFalse((self.root / "stale-repeat.json").exists())

    def assert_repeat_rejects_followup(self, name):
        self.assertEqual(self.plan_promotion().returncode, 0)
        self.assertEqual(self.promote("published").returncode, 0)
        target = self.destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("Changed after accepted promotion\n")
        self.git(self.destination, "add", "--", name)
        self.git(self.destination, "commit", "-qm", "Follow-up source")
        self.git(self.destination, "push", "-q", "origin", "HEAD")
        before = self.git(self.destination, "rev-parse", "HEAD")
        result = self.promote("repeated")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Previously promoted source changed", result.stderr)
        self.assertEqual(self.git(self.destination, "rev-parse", "HEAD"), before)

    def test_repeat_plan_rejects_an_unrelated_followup_commit(self):
        self.assert_repeat_rejects_followup("stock.txt")

    def test_repeat_plan_rejects_a_controller_followup_commit(self):
        self.assert_repeat_rejects_followup("databricks/tools/followup.py")

    def test_changed_development_source_stops_before_mutating_the_destination(self):
        self.assertEqual(self.plan_promotion().returncode, 0)
        (self.source / "databricks/README.md").write_text("Uncommitted source\n")
        result = self.promote("dirty")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be clean", result.stderr)
        self.assertFalse((self.destination / "databricks/app").exists())

    def test_unexpected_remote_branch_movement_is_not_overwritten(self):
        self.assertEqual(self.plan_promotion().returncode, 0)
        self.git(
            self.destination,
            "push",
            "-q",
            "origin",
            "HEAD:refs/heads/testing/databricks-port",
        )
        before = self.git(self.destination, "rev-parse", "HEAD")
        result = self.promote("moved")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("moved after promotion planning", result.stderr)
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ).split()[0],
            before,
        )
        self.assertFalse((self.destination / "databricks/app").exists())

    def test_git_publication_deploys_the_exact_promoted_commit_without_workspace_upload(
        self,
    ):
        self.assertEqual(self.plan_promotion().returncode, 0)
        self.assertEqual(self.promote("publication").returncode, 0)
        published = json.loads((self.root / "publication.json").read_text())
        resource = {
            "name": "installation-config",
            "secret": {"scope": "fixture", "key": "runtime", "permission": "READ"},
        }
        git_source = {
            "commit": published["head"],
            "resolved_commit": published["head"],
            "source_code_path": "databricks/app",
            "git_repository": {
                "url": "https://github.com/pi-squared/OpenContracts.git",
                "provider": "gitHub",
            },
        }
        app = {
            "name": "oc-fixture",
            "id": "fixture-app",
            "description": "owned",
            "url": "https://fixture.invalid",
            "resources": [resource],
            "git_repository": git_source["git_repository"],
            "compute_status": {"state": "ACTIVE"},
            "app_status": {"state": "RUNNING"},
            "active_deployment": {
                "status": {"state": "SUCCEEDED"},
                "git_source": git_source,
            },
        }
        calls = []

        class FakeCli:
            def __init__(self, *args):
                pass

            def run(self, arguments, **kwargs):
                calls.append(arguments)
                if arguments == ["apps", "get", "oc-fixture"]:
                    return app
                if arguments == ["secrets", "list-secrets", "fixture"]:
                    return {
                        "secrets": [{"key": "runtime", "last_updated_timestamp": 1}]
                    }
                if arguments[:2] == ["apps", "deploy"]:
                    return app["active_deployment"]
                raise AssertionError(arguments)

        directory = self.root / "installation"
        directory.mkdir()
        deployment.private_json(
            directory / "installation.json",
            {
                "installation": "fixture",
                "profile": "chosen",
                "app_name": "oc-fixture",
                "app_id": "fixture-app",
                "marker": "owned",
                "app_url": "https://fixture.invalid",
                "phase": "configured",
                "database_mode": "existing",
                "database_permissions_verified": True,
                "resources": [resource],
                "git_repository": git_source["git_repository"],
                "configuration_secret": {"scope": "fixture", "key": "runtime"},
                "configuration_secret_metadata": {
                    "key": "runtime",
                    "last_updated_timestamp": 1,
                },
            },
        )
        args = SimpleNamespace(
            state_directory=directory,
            installation="fixture",
            profile="chosen",
            cli=Path("/unused"),
            release=self.release,
            receipt=self.gate,
            python=Path(sys.executable),
            promotion_receipt=self.root / "publication.json",
            git_checkout=self.destination,
            verification_source=self.source / "databricks",
        )
        with patch.object(deployment, "Cli", FakeCli):
            deployment.publish_git(args)
        command = next(
            arguments for arguments in calls if arguments[:2] == ["apps", "deploy"]
        )
        self.assertEqual(command[command.index("--git-commit") + 1], published["head"])
        self.assertEqual(
            command[command.index("--git-source-code-path") + 1], "databricks/app"
        )
        self.assertFalse(any(arguments[0] == "workspace" for arguments in calls))

    def test_two_promotions_can_roll_back_to_verified_history_without_branch_or_database_changes(
        self,
    ):
        self.assertEqual(self.plan_promotion().returncode, 0)
        first = self.promote("release-a")
        self.assertEqual(first.returncode, 0, first.stderr)
        published_a = json.loads((self.root / "release-a.json").read_text())
        release_a, gate_a, source_a = self.release, self.gate, self.source
        historical = self.root / "historical-a"
        self.git(
            self.destination,
            "worktree",
            "add",
            "--detach",
            str(historical),
            published_a["head"],
        )
        self.source = self.root / "development-b"
        subprocess.run(
            ["git", "clone", "--quiet", str(source_a), str(self.source)], check=True
        )
        self.git(self.source, "config", "user.name", "Fixture")
        self.git(self.source, "config", "user.email", "fixture@example.invalid")
        recipe_b = json.loads(
            (self.source / "databricks/upstream.lock.json").read_text()
        )
        recipe_b["fixture_release"] = "B"
        (self.source / "databricks/upstream.lock.json").write_text(json.dumps(recipe_b))
        (self.source / "databricks/README.md").write_text("Development release B\n")
        self.git(
            self.source,
            "add",
            "--",
            "databricks/README.md",
            "databricks/upstream.lock.json",
        )
        self.git(self.source, "commit", "-qm", "Release B")
        self.source_commit = self.git(self.source, "rev-parse", "HEAD")
        self.release = self.root / "release-b"
        shutil.copytree(release_a, self.release)
        (self.release / "app.py").write_text("print('release B')\n")
        manifest_b = json.loads((self.release / "release.json").read_text())
        manifest_b["lock_sha256"] = hashlib.sha256(
            (self.source / "databricks/upstream.lock.json").read_bytes()
        ).hexdigest()
        (self.release / "release.json").write_text(json.dumps(manifest_b))
        self.gate = self.root / "gate-b.json"
        gate = json.loads(gate_a.read_text())
        gate.update(
            release_directory=str(self.release),
            staged_files=inventory(self.release),
            source_directory=str(self.source / "databricks"),
            source_files=source_identity(self.source / "databricks"),
        )
        self.gate.write_text(json.dumps(gate))
        self.plan = self.root / "plan-b.json"
        self.assertEqual(self.plan_promotion().returncode, 0)
        second = self.promote("release-b")
        self.assertEqual(second.returncode, 0, second.stderr)
        published_b = json.loads((self.root / "release-b.json").read_text())
        resources = [
            {
                "name": "installation-config",
                "secret": {"scope": "fixture", "key": "runtime", "permission": "READ"},
            }
        ]
        repository = {
            "url": "https://github.com/pi-squared/OpenContracts.git",
            "provider": "gitHub",
        }
        app = {
            "name": "oc-fixture",
            "id": "fixture-app",
            "description": "owned",
            "url": "https://fixture.invalid",
            "resources": resources,
            "git_repository": repository,
            "compute_status": {"state": "ACTIVE"},
            "app_status": {"state": "RUNNING"},
            "active_deployment": {
                "status": {"state": "SUCCEEDED"},
                "git_source": {
                    "resolved_commit": published_b["head"],
                    "source_code_path": "databricks/app",
                    "git_repository": repository,
                },
            },
        }
        app_file = self.root / "external-app.json"
        app_file.write_text(json.dumps(app))
        calls_file = self.root / "external-calls.jsonl"
        adapter = self.root / "databricks-fixture"
        adapter.write_text(
            "#!"
            + sys.executable
            + "\n"
            + f"APP = {str(app_file)!r}\nCALLS = {str(calls_file)!r}\n"
            + """import json, sys
from pathlib import Path
args = sys.argv[1:]
if args == ['version']:
    print('Databricks CLI v1.20.0')
    sys.exit(0)
args = args[:args.index('--profile')]
with Path(CALLS).open('a') as stream: stream.write(json.dumps(args) + chr(10))
app = json.loads(Path(APP).read_text())
if args == ['apps', 'get', 'oc-fixture']:
    result = app
elif args == ['secrets', 'list-secrets', 'fixture']:
    result = {'secrets': [{'key': 'runtime', 'last_updated_timestamp': 1}]}
elif args[:2] == ['apps', 'deploy']:
    app['active_deployment']['git_source']['resolved_commit'] = args[args.index('--git-commit') + 1]
    Path(APP).write_text(json.dumps(app))
    result = app['active_deployment']
else:
    raise AssertionError(args)
print(json.dumps(result))
"""
        )
        adapter.chmod(0o700)
        directory = self.root / "installation"
        deployment.private_json(
            directory / "installation.json",
            {
                "installation": "fixture",
                "profile": "chosen",
                "app_name": "oc-fixture",
                "app_id": "fixture-app",
                "marker": "owned",
                "app_url": "https://fixture.invalid",
                "phase": "configured",
                "database_mode": "existing",
                "database": "existing-database",
                "branch": "existing-lakebase-branch",
                "schema": "existing_schema",
                "database_permissions_verified": True,
                "resources": resources,
                "git_repository": repository,
                "configuration_secret": {"scope": "fixture", "key": "runtime"},
                "configuration_secret_metadata": {
                    "key": "runtime",
                    "last_updated_timestamp": 1,
                },
            },
        )
        command = [
            sys.executable,
            str(ROOT / "tools/deploy_installation.py"),
            "--cli",
            str(adapter),
            "--profile",
            "chosen",
            "--installation",
            "fixture",
            "--state-directory",
            str(directory),
            "rollback-git",
            "--release",
            str(release_a),
            "--receipt",
            str(gate_a),
            "--python",
            sys.executable,
            "--promotion-receipt",
            str(self.root / "release-a.json"),
            "--git-checkout",
            str(historical),
            "--verification-source",
            str(source_a / "databricks"),
            "--expected-remote-commit",
            published_b["head"],
        ]
        self.assertNotEqual(
            published_a["promotion"]["recipe_sha256"],
            published_b["promotion"]["recipe_sha256"],
        )
        stale_remote = subprocess.run(
            [*command[:-1], published_a["head"]], capture_output=True, text=True
        )
        self.assertNotEqual(stale_remote.returncode, 0)
        self.assertIn("Published testing source moved", stale_remote.stderr)
        self.assertFalse(calls_file.exists())
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["git_commit"], published_a["head"])
        self.assertEqual(
            self.git(
                self.destination,
                "ls-remote",
                "origin",
                "refs/heads/testing/databricks-port",
            ).split()[0],
            published_b["head"],
        )
        state = json.loads((directory / "installation.json").read_text())
        self.assertEqual(
            (state["database"], state["branch"], state["schema"]),
            ("existing-database", "existing-lakebase-branch", "existing_schema"),
        )
        calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
        self.assertFalse(
            any(call[0] in ("workspace", "postgres", "bundle") for call in calls)
        )
        self.assertEqual(
            json.loads(app_file.read_text())["active_deployment"]["git_source"][
                "resolved_commit"
            ],
            published_a["head"],
        )

        wrong_source = command.copy()
        wrong_source[wrong_source.index("--verification-source") + 1] = str(
            self.source / "databricks"
        )
        before = calls_file.read_text()
        rejected = subprocess.run(wrong_source, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn(
            "Selected historical verification source differs", rejected.stderr
        )
        self.assertEqual(calls_file.read_text(), before)
        changed_app = json.loads(app_file.read_text())
        changed_app["resources"] = []
        app_file.write_text(json.dumps(changed_app))
        rejected = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("App resource bindings changed", rejected.stderr)
        self.assertEqual(
            sum(
                json.loads(line)[:2] == ["apps", "deploy"]
                for line in calls_file.read_text().splitlines()
            ),
            1,
        )


if __name__ == "__main__":
    unittest.main()
