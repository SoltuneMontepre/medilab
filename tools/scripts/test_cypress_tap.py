"""Check Tap session routing and CLI isolation without starting Cypress."""

import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest.mock import patch

import cypress_tap as tap


def session(pid=123, **changes):
    row = {
        "pid": pid,
        "projectRoot": str(tap.TESTS),
        "testingType": "e2e",
        "browserSupported": True,
    }
    return row | changes


class TestCypressTap(unittest.TestCase):
    def call(self, arguments, rows, *, dispatched=0):
        discovery = subprocess.CompletedProcess([], 0, json.dumps(rows), "")
        result = subprocess.CompletedProcess([], dispatched, "", "")
        with patch.object(tap, "invoke", side_effect=[discovery, result]) as invoke:
            status = tap.run(arguments)
        return status, invoke

    def test_automatically_binds_only_the_current_worktree(self):
        rows = [session(1, projectRoot=str(tap.ROOT.parent / "other/src/tests")), session(9)]
        status, invoke = self.call(["status", "--json"], rows)
        self.assertEqual(status, 0)
        self.assertEqual(invoke.call_args.args[0], ["status", "--json", "--session", "9"])

    def test_refuses_to_fall_back_to_another_project(self):
        with self.assertRaisesRegex(tap.TapError, "No matching"):
            self.call(["run", "cypress/e2e/login.cy.js"], [session(projectRoot="/another/project")])

    def test_refuses_component_sessions_in_the_same_project(self):
        with self.assertRaisesRegex(tap.TapError, "No matching"):
            self.call(["status"], [session(testingType="component")])

    def test_refuses_multiple_matching_sessions_without_a_pid(self):
        with self.assertRaisesRegex(tap.TapError, "Several"):
            self.call(["status"], [session(10), session(11)])

    def test_explicit_pid_is_validated_and_forwarded_once(self):
        for option in (["--session", "11"], ["-s", "11"], ["--session=11"]):
            with self.subTest(option=option):
                status, invoke = self.call(["status", *option, "--json"], [session(10), session(11)])
                self.assertEqual(status, 0)
                self.assertEqual(invoke.call_args.args[0], ["status", "--json", "--session", "11"])

    def test_explicit_pid_cannot_select_another_project(self):
        with self.assertRaisesRegex(tap.TapError, "No matching"):
            self.call(["status", "--session", "10"], [session(10, projectRoot="/another"), session(11)])

    def test_rejects_missing_duplicate_or_invalid_session_values(self):
        for arguments in (["status", "-s"], ["status", "-s", "-1"], ["status", "-s", "1", "-s", "2"]):
            with self.subTest(arguments=arguments), self.assertRaises(tap.TapError):
                tap.extract_session(arguments)

    def test_rejects_an_unsupported_browser(self):
        with self.assertRaisesRegex(tap.TapError, "Electron"):
            self.call(["status"], [session(browserSupported=False)])

    def test_session_listing_contains_only_current_e2e_sessions(self):
        rows = [session(10), session(11, testingType="component"), session(12, projectRoot="/another")]
        with contextlib.redirect_stdout(io.StringIO()) as output:
            status, invoke = self.call(["sessions", "--json"], rows)
        self.assertEqual(status, 0)
        self.assertEqual([row["pid"] for row in json.loads(output.getvalue())], [10])
        self.assertEqual(invoke.call_count, 1)

    def test_blank_or_non_array_discovery_is_not_a_session(self):
        for payload in ("", "No running Cypress session found.", "{}"):
            with self.subTest(payload=payload):
                result = subprocess.CompletedProcess([], 0, payload, "")
                with patch.object(tap, "invoke", return_value=result), self.assertRaises(tap.TapError):
                    tap.run(["status"])

    def test_discovery_failure_preserves_exit_status_and_output(self):
        result = subprocess.CompletedProcess([], 23, "incompatible CLI\n", "renderer failed\n")
        with (
            patch.object(tap, "invoke", return_value=result) as invoke,
            contextlib.redirect_stdout(io.StringIO()) as out,
            contextlib.redirect_stderr(io.StringIO()) as err,
        ):
            self.assertEqual(tap.run(["status"]), 23)
        self.assertIn("incompatible CLI", out.getvalue())
        self.assertIn("renderer failed", err.getvalue())
        self.assertEqual(invoke.call_count, 1)

    def test_command_failure_is_not_reported_as_success(self):
        status, _ = self.call(["reporter"], [session()], dispatched=23)
        self.assertEqual(status, 23)

    def test_task_arguments_are_data_and_keep_quoted_selectors(self):
        value = 'dom --selector "$(echo unsafe)" --max-chars 6000'
        with patch.dict(os.environ, {"MEDILAB_TAP_ARGS": value}), patch.object(tap.sys, "argv", ["cypress_tap.py"]):
            status, invoke = self.call(None, [session()])
        self.assertEqual(status, 0)
        self.assertEqual(
            invoke.call_args.args[0],
            ["dom", "--selector", "$(echo unsafe)", "--max-chars", "6000", "--session", "123"],
        )

    def test_help_needs_neither_a_session_nor_dependencies(self):
        with patch.object(tap, "invoke") as invoke, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(tap.run(["--help"]), 0)
        self.assertIn("test:e2e:tap:open", output.getvalue())
        invoke.assert_not_called()

    def test_cli_uses_local_package_cwd_and_clears_electron_node_mode(self):
        result = subprocess.CompletedProcess([], 0)
        with (
            patch.object(tap.shutil, "which", return_value="node"),
            patch.object(tap.Path, "is_file", return_value=True),
            patch.object(tap.Path, "read_text", return_value='{"version":"16.2.0"}'),
            patch.dict(os.environ, {"ELECTRON_RUN_AS_NODE": "1"}),
            patch.object(tap.subprocess, "run", return_value=result) as run,
        ):
            self.assertIs(tap.invoke(["status", "--json"]), result)
        command = run.call_args.args[0]
        self.assertEqual(
            command, ["node", str(tap.TESTS / "node_modules/cypress/bin/cypress"), "tap", "status", "--json"]
        )
        self.assertEqual(run.call_args.kwargs["cwd"], tap.TESTS)
        self.assertNotIn("ELECTRON_RUN_AS_NODE", run.call_args.kwargs["env"])

    def test_old_cypress_is_refused_before_probing_tap(self):
        with (
            patch.object(tap.shutil, "which", return_value="node"),
            patch.object(tap.Path, "is_file", return_value=True),
            patch.object(tap.Path, "read_text", return_value='{"version":"15.20.0"}'),
            patch.object(tap.subprocess, "run") as run,
            self.assertRaisesRegex(tap.TapError, "15.21.0"),
        ):
            tap.invoke(["status"])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
