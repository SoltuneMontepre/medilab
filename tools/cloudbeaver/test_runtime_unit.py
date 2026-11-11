"""Validate the local container executable boundary without starting an engine."""

import os
import subprocess
import unittest
from unittest.mock import Mock, patch

from runtime import Runtime, engine


class TestRuntimeUnit(unittest.TestCase):
    def test_wait_refreshes_a_restarted_containers_ephemeral_port(self):
        runtime = Runtime.__new__(Runtime)
        runtime.name = "disposable-test-container"
        runtime.port = 30001

        def query(_):
            self.assertEqual(runtime.port, 30002)
            return {"data": {"serverConfig": {"configurationMode": False}}}

        runtime.query = query
        with patch("runtime.engine", return_value=Mock(stdout="127.0.0.1:30002\n")) as command:
            runtime.wait()
        command.assert_called_once_with("port", runtime.name, "8978")

    def test_default_docker_passes_arguments_without_a_shell(self):
        with patch.dict(os.environ, {}, clear=True), patch("runtime.subprocess.run") as run:
            run.return_value = Mock(returncode=0)
            engine("inspect", "literal;$(never-execute)")
            self.assertEqual(run.call_args.args[0], ["docker", "inspect", "literal;$(never-execute)"])
            self.assertFalse(run.call_args.kwargs.get("shell", False))

    def test_explicit_podman_is_supported(self):
        with patch.dict(os.environ, {"CONTAINER_ENGINE": "podman"}), patch("runtime.subprocess.run") as run:
            run.return_value = Mock(returncode=0)
            engine("info")
            self.assertEqual(run.call_args.args[0], ["podman", "info"])

    def test_container_timeout_is_bounded_and_redacts_arguments_and_output(self):
        failure = subprocess.TimeoutExpired(
            ["docker", "run", "SECRET-ARGUMENT"], 12, output="SECRET-OUTPUT", stderr="SECRET-ERROR"
        )
        with patch("runtime.subprocess.run", side_effect=failure) as run:
            with self.assertRaisesRegex(RuntimeError, "run timed out after 12s") as caught:
                engine("run", "SECRET-ARGUMENT", timeout=12)
            self.assertEqual(run.call_args.kwargs["timeout"], 12)
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertTrue(caught.exception.__suppress_context__)

    def test_default_timeout_and_redacted_exit_failure(self):
        with patch("runtime.subprocess.run", return_value=Mock(returncode=3)) as run:
            with self.assertRaisesRegex(RuntimeError, "operation inspect failed \\(exit 3\\)"):
                engine("inspect", "SECRET-ARGUMENT")
            self.assertEqual(run.call_args.kwargs["timeout"], 600)

    def test_unknown_executables_and_embedded_arguments_are_rejected(self):
        for selected in ("sh", "/tmp/docker", "docker --context production", "podman --remote", ""):
            with (
                self.subTest(selected=selected),
                patch.dict(os.environ, {"CONTAINER_ENGINE": selected}),
                patch("runtime.subprocess.run") as run,
            ):
                with self.assertRaisesRegex(ValueError, "must be docker or podman"):
                    engine("info")
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
