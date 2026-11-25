"""Cloud session start: the hook only acts in a cloud session, and Odoo starts from the seed without needless work."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import call, patch

import cloud_start

CONFIG = {
    "services": {
        "postgres": {"image": "docker.io/library/postgres:18"},
        "odoo": {"ports": [{"published": "8069"}]},
    },
    "volumes": {
        "medilab-db": {"name": "medilab_medilab-db"},
        "medilab-app": {"name": "medilab_medilab-app"},
        "medilab-garage": {"name": "medilab_medilab-garage"},
    },
}


class HookTest(unittest.TestCase):
    def test_hook_does_nothing_outside_a_cloud_session(self):
        output = io.StringIO()
        with (
            patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": ""}),
            patch("cloud_start.subprocess.Popen") as popen,
            redirect_stdout(output),
        ):
            cloud_start.hook()
        popen.assert_not_called()
        self.assertEqual(output.getvalue(), "")

    def test_hook_starts_the_run_in_its_own_session_and_returns(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "cloud-start.log"
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"CLAUDE_CODE_REMOTE": "true"}),
                patch("cloud_start.ensure_local_directory"),
                patch("cloud_start.LOG", log),
                patch("cloud_start.subprocess.Popen") as popen,
                redirect_stdout(output),
            ):
                cloud_start.hook()
        arguments, options = popen.call_args
        self.assertEqual(arguments[0][-1], "run")
        self.assertTrue(options["start_new_session"])
        self.assertIn(cloud_start.READY_MESSAGE, output.getvalue())


class RunTest(unittest.TestCase):
    def run_start(self, *, database_exists, saved_commit):
        with (
            patch("cloud_start.SETUP_LOG", Path("missing-setup.log")),
            patch("cloud_start.os.chdir"),
            patch("cloud_start.start_docker"),
            patch("cloud_start.write_compose_env"),
            patch("cloud_start.compose_config", return_value=CONFIG),
            patch("cloud_start.volume_exists", return_value=database_exists),
            patch("cloud_start.restore") as restore,
            patch("cloud_start.head", return_value="abc"),
            patch("cloud_start.saved_commit", return_value=saved_commit),
            patch("cloud_start.task", return_value="task"),
            patch("cloud_start.STATE") as state,
            patch("cloud_start.compose") as compose,
            patch("cloud_start.subprocess.run") as run,
            patch("cloud_start.wait_until_ready"),
        ):
            cloud_start.run()
        return restore, state, compose, run

    def test_a_missing_database_is_restored_and_its_modules_upgraded(self):
        restore, state, compose, run = self.run_start(
            database_exists=False, saved_commit="abc"
        )
        restore.assert_called_once_with(CONFIG)
        upgrade = run.call_args.args[0]
        self.assertEqual(upgrade[:2], ["task", "upgrade"])
        self.assertNotIn("base", upgrade[2].removeprefix("MODULES=").split(","))
        state.write_text.assert_called_once()
        compose.assert_not_called()

    def test_a_resumed_session_on_the_same_commit_only_starts_the_stack(self):
        restore, state, compose, run = self.run_start(
            database_exists=True, saved_commit="abc"
        )
        restore.assert_not_called()
        run.assert_not_called()
        state.write_text.assert_not_called()
        compose.assert_called_once_with(["up", "-d", "--no-build"])

    def test_a_new_commit_upgrades_the_existing_database(self):
        restore, _state, _compose, run = self.run_start(
            database_exists=True, saved_commit="old"
        )
        restore.assert_not_called()
        self.assertEqual(run.call_args.args[0][:2], ["task", "upgrade"])


class RestoreTest(unittest.TestCase):
    def test_a_failed_restore_removes_the_volumes_it_created(self):
        with (
            patch("cloud_start.subprocess.run") as run,
            patch("cloud_start.compose") as compose,
            patch("cloud_start.fill_volumes", side_effect=RuntimeError("copy failed")),
            self.assertRaises(RuntimeError),
        ):
            cloud_start.restore(CONFIG)
        self.assertEqual(compose.call_args_list[-1], call(["down"]))
        self.assertEqual(
            run.call_args.args[0],
            [
                "docker",
                "volume",
                "rm",
                "medilab_medilab-db",
                "medilab_medilab-app",
                "medilab_medilab-garage",
            ],
        )


if __name__ == "__main__":
    unittest.main()
