"""typecheck.py passes only a complete pyright run that found no errors and no missing imported names."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import typecheck

CASE = """from odoo.addons.sol_laboratory.constants.models import (
    MODEL_UNKNOWN,
)

NAME = MODEL_UNKNOWN.upper()
"""


class TestPyrightReport(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.case = Path(folder.name, "case.py")
        self.case.write_text(CASE, encoding="utf-8")
        typecheck.import_lines.cache_clear()

    def diagnostic(self, line, severity="warning", rule=typecheck.IMPORT_NAME_RULE, file=None):
        return {
            "file": str(file or self.case),
            "severity": severity,
            "message": f"{severity} on line {line}",
            "range": {
                "start": {"line": line, "character": 4},
                "end": {"line": line, "character": 17},
            },
            "rule": rule,
        }

    def report(self, *diagnostics, files=1, errors=None):
        errors = sum(item["severity"] == "error" for item in diagnostics) if errors is None else errors
        warnings = sum(item["severity"] == "warning" for item in diagnostics)
        summary = {
            "filesAnalyzed": files,
            "errorCount": errors,
            "warningCount": warnings,
            "informationCount": 0,
        }
        return json.dumps(
            {
                "version": "1.1.414",
                "generalDiagnostics": list(diagnostics),
                "summary": summary,
            }
        )

    def outcome(self, returncode, stdout, stderr=""):
        """The exit code, standard output and standard error of the typecheck of a pyright run."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = typecheck.outcome(subprocess.CompletedProcess([], returncode, stdout, stderr))
        return code, out.getvalue(), err.getvalue()

    def test_odoo_warnings_pass(self):
        code, out, _ = self.outcome(
            0,
            self.report(self.diagnostic(4), self.diagnostic(4, rule="reportArgumentType")),
        )
        self.assertEqual(code, 0)
        self.assertIn("0 errors, 2 warnings in 1 files", out)

    def test_a_missing_imported_name_fails(self):
        code, out, _ = self.outcome(0, self.report(self.diagnostic(1), self.diagnostic(4)))
        self.assertEqual(code, 1)
        self.assertIn(
            f"{self.case}:2:5 - error: warning on line 1 ({typecheck.IMPORT_NAME_RULE})",
            out,
        )
        self.assertIn("1 errors, 1 warnings in 1 files", out)

    def test_an_error_fails(self):
        code, out, _ = self.outcome(1, self.report(self.diagnostic(4, "error", "reportAssignmentType")))
        self.assertEqual(code, 1)
        self.assertIn("error on line 4 (reportAssignmentType)", out)

    def test_an_import_warning_in_a_file_that_cannot_be_read_fails(self):
        diagnostic = self.diagnostic(4, file=self.case.with_name("gone.py"))
        code, _, _ = self.outcome(0, self.report(diagnostic))
        self.assertEqual(code, 1)

    def test_a_failed_run_with_an_empty_report_fails(self):
        stderr = 'Config file "pyrightconfig.json" could not be parsed. Verify that format is correct.\n'
        code, out, err = self.outcome(3, self.report(files=0), stderr)
        self.assertEqual(code, 2)
        self.assertIn("could not be parsed", err)
        self.assertIn("pyright exited with 3", err)
        self.assertIn("0 errors, 0 warnings in 0 files", out)

    def test_a_failed_run_with_errors_keeps_them_visible(self):
        code, out, err = self.outcome(2, self.report(self.diagnostic(4, "error", "reportAssignmentType")))
        self.assertEqual(code, 2)
        self.assertIn("error on line 4", out)
        self.assertIn("pyright exited with 2", err)

    def test_a_run_that_checked_no_files_fails(self):
        code, _, err = self.outcome(0, self.report(files=0), 'File or directory "nothing" does not exist.\n')
        self.assertEqual(code, 2)
        self.assertIn("checked no files", err)
        self.assertIn("does not exist", err)

    def test_an_exit_code_of_errors_without_errors_fails(self):
        code, _, err = self.outcome(1, self.report(self.diagnostic(4)))
        self.assertEqual(code, 2)
        self.assertIn("but listed 0", err)

    def test_counted_errors_that_are_not_listed_fail(self):
        code, _, err = self.outcome(0, self.report(errors=2))
        self.assertEqual(code, 2)
        self.assertIn("counted 2 errors, but listed 0", err)

    def test_an_incomplete_report_fails(self):
        stdout = self.report(self.diagnostic(4))[:-20]
        code, _, err = self.outcome(0, stdout)
        self.assertEqual(code, 2)
        self.assertIn("no complete report", err)
        self.assertIn(stdout, err)

    def test_a_report_without_counts_fails(self):
        report = json.loads(self.report())
        del report["summary"]["errorCount"]
        code, _, _ = self.outcome(0, json.dumps(report))
        self.assertEqual(code, 2)

    def test_a_diagnostic_without_a_place_fails(self):
        diagnostic = self.diagnostic(4)
        del diagnostic["range"]
        code, _, _ = self.outcome(0, self.report(diagnostic))
        self.assertEqual(code, 2)

    def test_a_report_that_is_not_an_object_fails(self):
        code, _, _ = self.outcome(0, "[]")
        self.assertEqual(code, 2)

    def test_a_crash_without_output_fails_and_shows_why(self):
        code, _, err = self.outcome(1, "", "No module named pyright\n")
        self.assertEqual(code, 2)
        self.assertIn("No module named pyright", err)

    def test_a_killed_run_fails(self):
        code, _, _ = self.outcome(-9, self.report())
        self.assertEqual(code, 2)

    def test_the_command_line_exits_with_the_outcome(self):
        failed = subprocess.CompletedProcess([], 3, self.report(files=0), "")
        with (
            mock.patch.object(sys, "argv", ["typecheck.py"]),
            mock.patch.object(typecheck.subprocess, "run", return_value=failed),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as exited:
                typecheck.main()
        self.assertEqual(exited.exception.code, 2)

    def test_invalid_report_shapes_fail_cleanly(self):
        for report in (
            None,
            {"summary": [], "generalDiagnostics": []},
            {
                "summary": {"filesAnalyzed": 1, "errorCount": 0, "warningCount": 0},
                "generalDiagnostics": {},
            },
        ):
            with self.subTest(report=report):
                code, _, err = self.outcome(0, json.dumps(report))
                self.assertEqual(code, 2)
                self.assertIn("no complete report", err)

    def test_non_json_numeric_constants_fail(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                report = self.report().replace(
                    '"informationCount": 0', f'"informationCount": 0, "timeInSec": {constant}'
                )
                code, _, _ = self.outcome(0, report)
                self.assertEqual(code, 2)

    def test_invalid_counts_fail(self):
        for key in ("filesAnalyzed", "errorCount", "warningCount", "informationCount"):
            for value in (-1, True, "1", None):
                with self.subTest(key=key, value=value):
                    report = json.loads(self.report())
                    report["summary"][key] = value
                    code, _, _ = self.outcome(0, json.dumps(report))
                    self.assertEqual(code, 2)

    def test_inconsistent_warning_and_information_counts_fail(self):
        for key in ("warningCount", "informationCount"):
            with self.subTest(key=key):
                report = json.loads(self.report())
                report["summary"][key] = 1
                code, _, _ = self.outcome(0, json.dumps(report))
                self.assertEqual(code, 2)

    def test_invalid_diagnostics_fail_cleanly(self):
        for change in (
            {"severity": "fatal"},
            {"range": {"start": {"line": -1, "character": 0}, "end": {"line": 4, "character": 17}}},
            {"range": {"start": {"line": True, "character": 0}, "end": {"line": 4, "character": 17}}},
            {"range": {"start": {"line": 1, "character": 0}}},
            {
                "range": {
                    "start": {"line": 2, "character": 0},
                    "end": {"line": 1, "character": 0},
                }
            },
        ):
            with self.subTest(change=change):
                code, _, _ = self.outcome(0, self.report(self.diagnostic(4) | change))
                self.assertEqual(code, 2)

    def test_unexpected_execution_failures_are_reported(self):
        for error in (
            FileNotFoundError("python"),
            OSError("cannot execute"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid"),
        ):
            with self.subTest(error=error):
                err = io.StringIO()
                with (
                    mock.patch.object(sys, "argv", ["typecheck.py"]),
                    mock.patch.object(typecheck.subprocess, "run", side_effect=error),
                    contextlib.redirect_stderr(err),
                    self.assertRaises(SystemExit) as exited,
                ):
                    typecheck.main()
                self.assertEqual(exited.exception.code, 2)
                self.assertIn(str(error), err.getvalue())

    def test_an_incomplete_information_count_fails(self):
        report = json.loads(self.report())
        del report["summary"]["informationCount"]
        code, _, _ = self.outcome(0, json.dumps(report))
        self.assertEqual(code, 2)

    def test_a_null_diagnostic_fails_cleanly(self):
        report = json.loads(self.report())
        report["generalDiagnostics"] = [None]
        code, _, _ = self.outcome(0, json.dumps(report))
        self.assertEqual(code, 2)

    def test_a_missing_diagnostic_message_fails(self):
        diagnostic = self.diagnostic(4)
        del diagnostic["message"]
        code, _, _ = self.outcome(0, self.report(diagnostic))
        self.assertEqual(code, 2)

    def test_a_timeout_is_reported(self):
        err = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["typecheck.py"]),
            mock.patch.object(
                typecheck.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired("pyright", 10),
            ),
            contextlib.redirect_stderr(err),
            self.assertRaises(SystemExit) as exited,
        ):
            typecheck.main()
        self.assertEqual(exited.exception.code, 2)
        self.assertIn("timed out", err.getvalue())


if __name__ == "__main__":
    unittest.main()
