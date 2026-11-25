"""Cloud session start: the hook only acts in a cloud session, and Odoo starts from the seed without needless work."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import nullcontext, redirect_stdout
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
            patch("cloud_start.ensure_local_directory"),
            patch("cloud_start.exclusive_lock", return_value=nullcontext()) as lock,
            patch("cloud_start.start_docker"),
            patch("cloud_start.write_compose_env"),
            patch("cloud_start.compose_config", return_value=CONFIG),
            patch("cloud_start.discard_unfinished_restore") as discard,
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
        lock.assert_called_once_with()
        discard.assert_called_once_with(CONFIG)
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


VOLUMES = ["medilab_medilab-db", "medilab_medilab-app", "medilab_medilab-garage"]


class RestoreTest(unittest.TestCase):
    def restore(self, journal, fill):
        with (
            patch("cloud_start.RESTORE_JOURNAL", journal),
            patch("cloud_start.subprocess.run") as run,
            patch("cloud_start.compose") as compose,
            patch("cloud_start.fill_volumes", side_effect=fill),
        ):
            run.return_value.returncode = 0
            cloud_start.restore(CONFIG)
        compose.assert_called_once_with(
            ["up", "--no-start", "--no-build", "postgres", "garage", "odoo"]
        )

    def test_the_journal_names_the_volumes_until_they_are_filled(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "cloud-restore.json"
            recorded = []

            def fill(_config):
                recorded.extend(
                    json.loads(journal.read_text(encoding="utf-8"))["volumes"]
                )

            self.restore(journal, fill)
            self.assertEqual(recorded, VOLUMES)
            self.assertFalse(journal.exists())

    def test_an_interrupted_restore_keeps_its_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "cloud-restore.json"
            with self.assertRaises(RuntimeError):
                self.restore(journal, RuntimeError("copy failed"))
            self.assertTrue(journal.exists())


class DiscardTest(unittest.TestCase):
    def discard(self, journal, *, removed):
        with (
            patch("cloud_start.RESTORE_JOURNAL", journal),
            patch("cloud_start.compose") as compose,
            patch("cloud_start.subprocess.run") as run,
            patch("cloud_start.volume_exists", return_value=not removed),
            redirect_stdout(io.StringIO()),
        ):
            cloud_start.discard_unfinished_restore(CONFIG)
        return compose, run

    def test_without_a_journal_nothing_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            compose, run = self.discard(
                Path(directory) / "cloud-restore.json", removed=True
            )
        compose.assert_not_called()
        run.assert_not_called()

    def test_the_volumes_of_an_unfinished_restore_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "cloud-restore.json"
            journal.write_text(json.dumps({"volumes": VOLUMES[:1]}), encoding="utf-8")
            compose, run = self.discard(journal, removed=True)
            self.assertFalse(journal.exists())
        self.assertEqual(compose.call_args_list, [call(["down"])])
        self.assertEqual(run.call_args.args[0], ["docker", "volume", "rm", VOLUMES[0]])

    def test_a_volume_that_stays_stops_the_start_and_keeps_the_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "cloud-restore.json"
            journal.write_text(json.dumps({"volumes": VOLUMES}), encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.discard(journal, removed=False)
            self.assertTrue(journal.exists())


class VolumeTest(unittest.TestCase):
    def test_a_volume_is_found_by_its_exact_name(self):
        with patch("cloud_start.subprocess.run") as run:
            run.return_value.stdout = "medilab_medilab-db-old\nmedilab_medilab-app\n"
            self.assertFalse(cloud_start.volume_exists("medilab_medilab-db"))
            self.assertTrue(cloud_start.volume_exists("medilab_medilab-app"))

    def test_an_unreachable_docker_is_not_a_missing_volume(self):
        error = subprocess.CalledProcessError(1, ["docker", "volume", "ls"])
        with (
            patch("cloud_start.subprocess.run", side_effect=error),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            cloud_start.volume_exists("medilab_medilab-db")


@unittest.skipIf(sys.platform == "win32", "cloud sessions run on Linux")
class LockTest(unittest.TestCase):
    def test_a_second_run_cannot_take_the_lock_until_the_first_ends(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "cloud-start.lock"
            with patch("cloud_start.LOCK", lock):
                with (
                    cloud_start.exclusive_lock(),
                    lock.open("a") as other,
                    self.assertRaises(BlockingIOError),
                ):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with lock.open("a") as other:
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)


if __name__ == "__main__":
    unittest.main()
