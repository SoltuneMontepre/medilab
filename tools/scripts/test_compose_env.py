import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from compose_env import (
    compose_project_name,
    main,
    project_name,
    selected_project_name,
    worktree_paths,
)
from onlyoffice_state import CONFIG_KEYS


class TestComposeEnv(unittest.TestCase):
    def test_real_unicode_git_worktree_and_task_pipeline_without_python_utf8_mode(self):
        source = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="compose kiểm tra ") as temporary:
            directory = Path(temporary)
            primary = directory / "main checkout"
            linked = directory / "kiểm tra demo"
            primary.mkdir()
            for file in (
                "tools/scripts/compose_env.py",
                "tools/scripts/onlyoffice_state.py",
                "tools/scripts/log.sh",
                "tools/taskfiles/dev.taskfile.yml",
            ):
                target = primary / file
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / file, target)
            (primary / "tools/infrastructure").mkdir()
            (primary / "tools/infrastructure/.gitkeep").write_text("", encoding="utf-8")
            (primary / "src/core").mkdir(parents=True)
            (primary / "src/core/pyproject.toml").write_text(
                '[project]\nname="compose-fixture"\nversion="0.0.0"\nrequires-python=">=3.12"\n'
                "dependencies=[]\n[tool.uv]\npackage=false\n",
                encoding="utf-8",
            )
            (primary / "taskfile.yml").write_text(
                'version: "3"\nincludes:\n  dev:\n    taskfile: tools/taskfiles/dev.taskfile.yml\n'
                "    dir: .\n    flatten: true\n",
                encoding="utf-8",
            )
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("GIT_")
            }
            environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")

            def git(*arguments):
                return subprocess.run(
                    ["git", *arguments],
                    cwd=primary,
                    env=environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )

            git("init", "--quiet")
            git("add", ".")
            git(
                "-c",
                "user.name=Compose fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            )
            git("worktree", "add", "--quiet", "--detach", str(linked))
            with (
                patch.dict(os.environ, environment, clear=True),
                contextlib.chdir(linked),
                patch("compose_env.MARKER", linked / ".local/demo-bootstrap.json"),
                patch(
                    "compose_env.SWITCH_JOURNAL",
                    linked / ".local/demo-bootstrap-switch.json",
                ),
            ):
                self.assertEqual(
                    worktree_paths(linked), [primary.resolve(), linked.resolve()]
                )
                expected = compose_project_name(linked, [primary, linked])
                self.assertEqual(project_name(), expected)
            environment.pop("PYTHONUTF8", None)
            environment["PYTHONIOENCODING"] = "ascii"
            environment["UV_PYTHON"] = sys.executable
            environment["UV_OFFLINE"] = "1"
            result = subprocess.run(
                ["task", "dev:compose-env"],
                cwd=linked,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(
                str((linked / "tools/infrastructure/.env").resolve()), result.stdout
            )
            self.assertEqual(
                (linked / "tools/infrastructure/.env").read_text(encoding="utf-8"),
                f"COMPOSE_PROJECT_NAME={expected}\n",
            )

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
                        "worktree": str(root.resolve()),
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

    def test_selection_change_drops_only_the_prior_optional_editor_identity(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "marker.json"
            env = directory / ".env"
            marker.write_text(
                json.dumps(
                    {
                        "project": "medilab-bootstrap-next",
                        "selected_project": True,
                        "worktree": str(root),
                        "config": {
                            "COMPOSE_PROJECT_NAME": "medilab-bootstrap-next",
                            "MEDILAB_DEMO_BOOTSTRAP_OWNER": "next-owner",
                        },
                    }
                )
            )
            env.write_text(
                "UNCHANGED=value\n" + "\n".join(f"{key}=old" for key in CONFIG_KEYS)
            )
            with (
                patch("compose_env.MARKER", marker),
                patch("compose_env.ENV_FILE", env),
            ):
                main()
            self.assertIn("UNCHANGED=value", env.read_text())
            self.assertTrue(all(key not in env.read_text() for key in CONFIG_KEYS))

    def test_ordinary_dev_setup_keeps_its_existing_editor_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            env = directory / ".env"
            env.write_text("\n".join(f"{key}=saved" for key in CONFIG_KEYS))
            with (
                patch("compose_env.MARKER", directory / "absent"),
                patch("compose_env.ENV_FILE", env),
                patch("compose_env.project_name", return_value="ordinary"),
            ):
                main()
            self.assertTrue(
                all(f"{key}=saved" in env.read_text() for key in CONFIG_KEYS)
            )


if __name__ == "__main__":
    unittest.main()
