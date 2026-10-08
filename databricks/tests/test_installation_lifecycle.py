"""Named installations retain ownership and their App during a resumed deployment."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from tools import deploy_installation as deployment


class LifecycleTests(unittest.TestCase):
    def args(self, directory):
        return SimpleNamespace(
            state_directory=directory,
            cli=Path("/unused"),
            profile="chosen",
            installation="fixture",
            extraction_endpoint="extract",
            embedding_endpoint="embed",
            grounding_endpoint="repair",
            definition_volume="catalog.schema.definitions",
        )

    def test_unknown_collision_fails_without_deployment_or_ownership_adoption(self):
        calls = []

        class FakeCli:
            def __init__(self, *args):
                pass

            def run(self, args, **kwargs):
                calls.append(args)
                return (
                    {
                        "profiles": [
                            {
                                "name": "chosen",
                                "host": "https://fixture.invalid",
                                "valid": True,
                            }
                        ]
                    }
                    if args == ["auth", "profiles"]
                    else ([{"name": "oc-fixture"}] if args == ["apps", "list"] else [])
                )

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deployment, "Cli", FakeCli),
        ):
            directory = Path(temporary)
            with self.assertRaisesRegex(ValueError, "collision"):
                deployment.provision(self.args(directory))
            self.assertFalse((directory / "installation.json").exists())
        self.assertFalse(any(args[0] == "bundle" for args in calls))

    def test_resuming_known_installation_keeps_app_in_every_bundle(self):
        marker = "owned installation"
        app = {
            "name": "oc-fixture",
            "id": "stable-app",
            "description": marker,
            "url": "https://fixture.invalid",
        }
        bundled_apps = []

        class FakeCli:
            def __init__(self, *args):
                pass

            def run(self, args, *, cwd=None):
                if args == ["auth", "profiles"]:
                    return {
                        "profiles": [
                            {
                                "name": "chosen",
                                "host": "https://fixture.invalid",
                                "valid": True,
                            }
                        ]
                    }
                if args == ["apps", "list"]:
                    return [app]
                if args == ["postgres", "list-projects"]:
                    return [
                        {
                            "name": "projects/oc-fixture",
                            "status": {"display_name": marker},
                        }
                    ]
                if args[:2] == ["bundle", "validate"]:
                    configuration = yaml.safe_load((cwd / "databricks.yml").read_text())
                    bundled_apps.append(configuration["resources"].get("apps"))
                    return {
                        "workspace": {
                            "root_path": "/Workspace/Users/fixture/install/bundle"
                        },
                        "resources": {
                            "apps": {"opencontracts": {"name": "oc-fixture"}}
                        },
                    }
                if args[:2] == ["bundle", "deploy"]:
                    return {}
                if args[:2] == ["postgres", "list-branches"]:
                    return [{"name": "projects/oc-fixture/branches/production"}]
                if args[:2] == ["postgres", "list-databases"]:
                    return [
                        {
                            "name": "projects/oc-fixture/branches/production/databases/db",
                            "status": {"postgres_database": "databricks_postgres"},
                        }
                    ]
                if args == ["apps", "get", "oc-fixture"]:
                    return app
                raise AssertionError(args)

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(deployment, "Cli", FakeCli),
        ):
            directory = Path(temporary)
            deployment.private_json(
                directory / "installation.json",
                {
                    "installation": "fixture",
                    "host": "https://fixture.invalid",
                    "profile": "chosen",
                    "app_name": "oc-fixture",
                    "project_id": "oc-fixture",
                    "marker": marker,
                    "phase": "provisioned",
                    "branch": "projects/oc-fixture/branches/production",
                    "database": "projects/oc-fixture/branches/production/databases/db",
                },
            )
            deployment.provision(self.args(directory))
            state = json.loads((directory / "installation.json").read_text())
            self.assertEqual(state["app_id"], "stable-app")
            self.assertEqual(state["marker"], marker)
        self.assertTrue(bundled_apps)
        self.assertTrue(all("opencontracts" in apps for apps in bundled_apps))


if __name__ == "__main__":
    unittest.main()
