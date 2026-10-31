"""Saved diagnostic reports retain the raw output and explain the warning distribution."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import typecheck


class TestReportFiles(unittest.TestCase):
    def test_counts_group_diagnostics_without_changing_the_report(self):
        diagnostic = {
            "file": str(
                typecheck.ROOT / "src/core/modules/sol_laboratory/models/example.py"
            ),
            "severity": "warning",
            "rule": "reportAttributeAccessIssue",
            "message": "unknown field",
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 0, "character": 1},
            },
        }
        raw = json.dumps(
            {
                "summary": {
                    "filesAnalyzed": 1,
                    "errorCount": 0,
                    "warningCount": 1,
                    "informationCount": 0,
                },
                "generalDiagnostics": [diagnostic],
            }
        )
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            typecheck.save_report(
                subprocess.CompletedProcess([], 0, raw, "stderr\n"), directory
            )
            self.assertEqual((directory / "pyright.json").read_text(), raw)
            self.assertEqual((directory / "pyright.stderr.txt").read_text(), "stderr\n")
            counts = json.loads((directory / "counts.json").read_text())
        self.assertEqual(counts["module"], {"sol_laboratory": 1})
        self.assertEqual(counts["rule"], {"reportAttributeAccessIssue": 1})
        self.assertEqual(counts["severity"], {"warning": 1})

    def test_malformed_reports_are_saved_without_inventing_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            typecheck.save_report(
                subprocess.CompletedProcess([], 3, "broken json", "failed"), directory
            )
            self.assertEqual((directory / "pyright.json").read_text(), "broken json")
            self.assertEqual(
                json.loads((directory / "counts.json").read_text()),
                {"exitCode": 3, "complete": False},
            )


if __name__ == "__main__":
    unittest.main()
