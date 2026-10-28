"""Runner lifecycle guards prevent false acceptance and stop only the selected owned process."""

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from . import run
from .native_results import NativeResults

SUCCESS_SUMMARY = "odoo.tests.result: 0 failed, 0 error(s) of 1 tests\n"


def result(code=0, stdout=""):
    return subprocess.CompletedProcess(["fixture"], code, stdout, "")


class TestRunner(unittest.TestCase):
    def test_timeout_stops_only_selected_runner_and_retains_logs(self):
        calls = []

        def engine(args, **options):
            calls.append(args)
            if "inspect" in args:
                return result(stdout=json.dumps([{"State": {"Running": True}}]))
            return result(stdout="Starting TestNative.test_save\n")

        with (
            patch.object(run, "command", side_effect=engine),
            patch.object(run.time, "monotonic", side_effect=[100, 102]),
        ):
            completed, observed = run.wait_for_runner(result(), 1)
        self.assertEqual(completed.returncode, 124)
        self.assertEqual(observed.statuses(124), {"TestNative.test_save": "BLOCKED"})
        self.assertEqual(
            [args for args in calls if "stop" in args], [[*run.DOCKER, "stop", "--time", "10", run.CONTAINER]]
        )
        self.assertFalse(any("rm" in args or "down" in args for args in calls))

    def test_failed_case_survives_engine_log_rotation(self):
        states = iter([True, False])
        logs = iter(
            [
                "Starting TestOnlyofficeReal.test_save\nFAIL: TestOnlyofficeReal.test_save\n",
                SUCCESS_SUMMARY,
                SUCCESS_SUMMARY,
            ]
        )

        def engine(args, **options):
            if "inspect" in args:
                return result(stdout=json.dumps([{"State": {"Running": next(states), "ExitCode": 0}}]))
            return result(stdout=next(logs))

        with patch.object(run, "command", side_effect=engine), patch.object(run.time, "sleep"):
            completed, observed = run.wait_for_runner(result(), 30)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(observed.statuses(0), {"TestOnlyofficeReal.test_save": "FAIL"})

    def test_existing_database_refuses_before_launch(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(run, "OUTPUT", Path(directory)),
            patch.object(run, "verify_image"),
            patch.object(run, "command", return_value=result(1)),
            patch.object(run, "compose", return_value=result(stdout="owned_database\n")) as compose,
        ):
            with self.assertRaisesRegex(RuntimeError, "database already exists"):
                run.test()
        self.assertEqual(compose.call_count, 1)
        self.assertEqual(compose.call_args.args[:3], ("exec", "-T", "postgres"))

    def receipt(self, *, started=True, native_only=True, copy_exit=0):
        observations = NativeResults()
        messages = SUCCESS_SUMMARY
        if started:
            messages = "Starting TestNative.test_save\n" + messages
        observations.observe(result(stdout=messages))
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(run, "OUTPUT", Path(directory)),
            patch.object(run, "check_test_run"),
            patch.object(run, "compose", return_value=result()),
            patch.object(run, "wait_for_runner", return_value=(result(stdout=messages), observations)),
            patch.object(run, "command", return_value=result(copy_exit)),
            patch.object(run, "write_result") as write,
            patch.dict(os.environ, {"ONLYOFFICE_TEST_METHOD": ""}),
        ):
            expectation = (
                nullcontext()
                if started and native_only
                else self.assertRaisesRegex(RuntimeError, "failed or lacks complete evidence")
            )
            with expectation:
                run.test(native_only=native_only)
        return write.call_args.args[1]

    def test_zero_test_summary_does_not_claim_acceptance(self):
        receipt = self.receipt(started=False)
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["native_test_status"], {})

    def test_real_run_without_callback_evidence_does_not_claim_acceptance(self):
        receipt = self.receipt(native_only=False, copy_exit=1)
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["evidence_copy_exit"], 1)
        self.assertTrue(receipt["not_started_tests"])

    def test_successful_native_run_records_status_and_hash_without_raw_logs(self):
        receipt = self.receipt()
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["native_test_status"], {"TestNative.test_save": "PASS"})
        self.assertEqual(len(receipt["runner_log_sha256"]), 64)
        self.assertFalse(receipt["real_service_executed"])
        self.assertNotIn("stdout", receipt)
        self.assertNotIn("stderr", receipt)
