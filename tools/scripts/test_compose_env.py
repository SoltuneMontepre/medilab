import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compose_env import compose_project_name, main, selected_project_name


class TestComposeEnv(unittest.TestCase):
    def test_selected_project_is_read_from_worktree_owned_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / ".local/demo-bootstrap.json"
            marker.parent.mkdir()
            marker.write_text(
                json.dumps(
                    {
                        "project": "medilab-bootstrap-test-01",
                        "selected_project": True,
                        "worktree": str(root),
                        "config": {"COMPOSE_PROJECT_NAME": "medilab-bootstrap-test-01"},
                    }
                ),
                encoding="utf-8",
            )
            with patch("compose_env.MARKER", marker):
                self.assertEqual(
                    selected_project_name(root), "medilab-bootstrap-test-01"
                )

    def test_selected_project_refuses_marker_from_another_worktree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / ".local/demo-bootstrap.json"
            marker.parent.mkdir()
            marker.write_text(
                json.dumps(
                    {
                        "project": "medilab-bootstrap-test-01",
                        "selected_project": True,
                        "worktree": "/different/worktree",
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch("compose_env.MARKER", marker),
                self.assertRaisesRegex(ValueError, "another worktree"),
            ):
                selected_project_name(root)

    def test_interrupted_switch_blocks_compose_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "marker.json"
            journal = root / "demo-bootstrap-switch.json"
            marker.write_text(json.dumps({"project": "medilab-bootstrap-test-01"}))
            journal.write_text("{}", encoding="utf-8")
            with (
                patch("compose_env.MARKER", marker),
                patch("compose_env.SWITCH_JOURNAL", journal),
                self.assertRaisesRegex(ValueError, "interrupted project switch"),
            ):
                selected_project_name(root)

    def test_dev_setup_restores_selected_identity_and_ports(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "marker.json"
            env = directory / ".env"
            marker.write_text(
                json.dumps(
                    {
                        "project": "medilab-bootstrap-test-01",
                        "selected_project": True,
                        "worktree": str(root),
                        "config": {
                            "COMPOSE_PROJECT_NAME": "medilab-bootstrap-test-01",
                            "MEDILAB_ODOO_PORT": "28069",
                        },
                    }
                ),
                encoding="utf-8",
            )
            env.write_text(
                "COMPOSE_PROJECT_NAME=medilab-07088fb8\nMEDILAB_ODOO_PORT=8069\n",
                encoding="utf-8",
            )
            with (
                patch("compose_env.MARKER", marker),
                patch("compose_env.ENV_FILE", env),
            ):
                main()
            values = env.read_text(encoding="utf-8")
            self.assertIn("COMPOSE_PROJECT_NAME=medilab-bootstrap-test-01", values)
            self.assertIn("MEDILAB_ODOO_PORT=28069", values)
            self.assertNotIn("medilab-07088fb8", values)

    def test_worktree_with_the_main_checkout_name_gets_an_isolated_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            main = root / "main" / "medilab"
            worktree = root / "worktrees" / "branch" / "medilab"
            main.mkdir(parents=True)
            worktree.mkdir(parents=True)

            self.assertEqual(compose_project_name(main, [main, worktree]), "medilab")
            self.assertRegex(
                compose_project_name(worktree, [main, worktree]),
                re.compile(r"^medilab-[0-9a-f]{8}$"),
            )


if __name__ == "__main__":
    unittest.main()
