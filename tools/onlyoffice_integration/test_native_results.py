"""Evidence must distinguish failures, missing cases and zero-test runs from acceptance."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from .native_results import NativeResults, callback_outcomes, expected_test_names

NATIVE_CASE = "TestNative.test_save"


def snapshot(messages):
    return subprocess.CompletedProcess([], 0, messages, "")


class TestNativeResults(unittest.TestCase):
    def test_rotated_logs_preserve_started_and_failed_cases(self):
        observed = NativeResults()
        observed.observe(snapshot("Starting TestOnlyofficeReal.test_save\nFAIL: TestOnlyofficeReal.test_save\n"))
        observed.observe(snapshot("odoo.tests.result: 0 failed, 0 error(s) of 1 tests\n"))
        observed.observe(snapshot("odoo.tests.result: 0 failed, 0 error(s) of 1 tests\n"))
        self.assertEqual(observed.statuses(0), {"TestOnlyofficeReal.test_save": "FAIL"})
        self.assertEqual(len(observed.summaries), 1)

    def test_last_summary_and_exit_status_control_acceptance(self):
        observed = NativeResults()
        observed.observe(
            snapshot("Starting TestNative.test_save\nodoo.tests.result: 0 failed, 0 error(s) of 1 tests\n")
        )
        self.assertEqual(observed.statuses(0), {NATIVE_CASE: "PASS"})
        self.assertEqual(observed.statuses(124), {NATIVE_CASE: "BLOCKED"})
        observed.observe(snapshot("odoo.tests.result: 0 failed, 1 error(s) of 1 tests\n"))
        self.assertFalse(observed.successful_summary())
        self.assertEqual(observed.statuses(0), {NATIVE_CASE: "BLOCKED"})

    def test_started_cases_without_a_summary_are_blocked(self):
        observed = NativeResults()
        observed.observe(snapshot("Starting TestNative.test_save\n"))
        self.assertEqual(observed.statuses(0), {NATIVE_CASE: "BLOCKED"})

    def test_callback_outcomes_keep_body_failures_unknown_and_missing_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            files = []
            for name, outcome in (("test_pass", True), ("test_fail", False), ("test_unknown", None)):
                path = Path(directory) / (name + ".json")
                path.write_text(json.dumps({"test_body_passed": outcome}), encoding="utf-8")
                files.append(path)
            logs = "Starting TestOnlyofficeReal.test_blocked\n"
            result = callback_outcomes(snapshot(logs), files, ["test_never_started"], False)
        self.assertEqual(
            result,
            {
                "failed_tests": ["test_fail"],
                "passed_tests": ["test_pass"],
                "unknown_outcome_tests": ["test_unknown"],
                "blocked_tests": ["test_blocked"],
                "not_started_tests": ["test_never_started"],
            },
        )

    def test_callback_failure_log_overrides_a_positive_body_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_save.json"
            path.write_text('{"test_body_passed": true}', encoding="utf-8")
            result = callback_outcomes(snapshot("ERROR: TestOnlyofficeReal.test_save\n"), [path], [], True)
        self.assertEqual(result["failed_tests"], ["test_save"])
        self.assertEqual(result["passed_tests"], [])

    def test_selected_real_cases_must_exist_and_native_mode_does_not_expect_callbacks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cases.py"
            source.write_text("def test_one(): pass\ndef test_two(): pass\n", encoding="utf-8")
            self.assertEqual(expected_test_names(source, False, "test_two"), ["test_two"])
            self.assertEqual(expected_test_names(source, True, None), [])
            with self.assertRaisesRegex(ValueError, "selected real-service test does not exist"):
                expected_test_names(source, False, "test_missing")
