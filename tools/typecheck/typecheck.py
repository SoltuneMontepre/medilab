"""Run pyright on the modules and fail on its errors and on imports of names that do not exist.

pyright reports "from <module> import <name>" of a missing name under reportAttributeAccessIssue, the rule that
pyrightconfig.json lowers to a warning for Odoo's dynamic models. This script reports those warnings as errors.
Files given as arguments are checked instead of the modules.
A pyright run that fails, writes no complete report or checks no files fails too, whatever it reported.
"""

import argparse
import ast
import functools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "pyrightconfig.json"
IMPORT_NAME_RULE = "reportAttributeAccessIssue"
SEVERITY_COUNTS = {
    "error": "errorCount",
    "warning": "warningCount",
    "information": "informationCount",
}
SUMMARY_COUNTS = ("filesAnalyzed", *SEVERITY_COUNTS.values())


@functools.cache
def import_lines(path):
    """The line numbers, from 0 as pyright counts them, of the "from ... import" statements in the file at path.

    None when the file cannot be parsed, so that every warning of the rule in it fails.
    """
    try:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)
    except (OSError, SyntaxError, ValueError):
        return None
    return {
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for line in range(node.lineno - 1, node.end_lineno or node.lineno)
    }


def fails(diagnostic):
    if diagnostic["severity"] == "error":
        return True
    if diagnostic.get("rule") != IMPORT_NAME_RULE:
        return False
    lines = import_lines(diagnostic["file"])
    return lines is None or diagnostic["range"]["start"]["line"] in lines


def describe(diagnostic):
    start = diagnostic["range"]["start"]
    rule = f" ({diagnostic['rule']})" if diagnostic.get("rule") else ""
    return f"{diagnostic['file']}:{start['line'] + 1}:{start['character'] + 1} - error: {diagnostic['message']}{rule}"


def checked_files():
    """The files given as arguments, as absolute paths, so pyright never reads one as an option."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="files to check instead of the modules")
    files = [path.resolve() for path in parser.parse_args().files]
    if missing := [str(path) for path in files if not path.is_file()]:
        parser.error(f"not a file: {', '.join(missing)}")
    return [str(path) for path in files]


def is_complete(diagnostic):
    if not isinstance(diagnostic, dict):
        return False
    if not all(isinstance(diagnostic[key], str) for key in ("file", "severity", "message")):
        return False
    if not diagnostic["file"] or diagnostic["severity"] not in SEVERITY_COUNTS:
        return False
    if "rule" in diagnostic and not isinstance(diagnostic["rule"], str):
        return False
    start, end = diagnostic["range"]["start"], diagnostic["range"]["end"]
    return all(
        type(position[key]) is int and position[key] >= 0 for position in (start, end) for key in ("line", "character")
    ) and (end["line"], end["character"]) >= (start["line"], start["character"])


def invalid_constant(value):
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def read_report(output):
    """The JSON report that pyright wrote to output, or None when it is missing or incomplete."""
    try:
        report = json.loads(output, parse_constant=invalid_constant)
        complete = (
            isinstance(report, dict)
            and isinstance(report["summary"], dict)
            and isinstance(report["generalDiagnostics"], list)
            and all(type(report["summary"][key]) is int and report["summary"][key] >= 0 for key in SUMMARY_COUNTS)
            and all(is_complete(diagnostic) for diagnostic in report["generalDiagnostics"])
        )
    except (ValueError, TypeError, KeyError):
        return None
    return report if complete else None


def broken_run(returncode, report):
    """Why a pyright run cannot be trusted, or None when it can."""
    if report is None:
        return f"pyright exited with {returncode} and wrote no complete report."
    if returncode not in (0, 1):
        return f"pyright exited with {returncode}, so it did not check the modules."
    summary = report["summary"]
    errors = sum(diagnostic["severity"] == "error" for diagnostic in report["generalDiagnostics"])
    if errors != summary["errorCount"] or (returncode == 1) != (errors > 0):
        return f"pyright exited with {returncode} and counted {summary['errorCount']} errors, but listed {errors}."
    for severity, count in SEVERITY_COUNTS.items():
        if sum(diagnostic["severity"] == severity for diagnostic in report["generalDiagnostics"]) != summary[count]:
            return f"pyright's {count} does not match its diagnostics."
    if not summary["filesAnalyzed"]:
        return "pyright checked no files."
    return None


def outcome(result):
    """Write what the pyright run in result found, and return the exit code: 1 for errors, 2 for a failed run."""
    sys.stderr.write(result.stderr)
    report = read_report(result.stdout)
    failures = []
    if report is None:
        sys.stderr.write(result.stdout)
    else:
        failures = [diagnostic for diagnostic in report["generalDiagnostics"] if fails(diagnostic)]
        for diagnostic in failures:
            sys.stdout.write(describe(diagnostic) + "\n")
        summary = report["summary"]
        warnings = summary["warningCount"] - (len(failures) - summary["errorCount"])
        sys.stdout.write(f"{len(failures)} errors, {warnings} warnings in {summary['filesAnalyzed']} files\n")
    if problem := broken_run(result.returncode, report):
        sys.stderr.write(f"error: {problem}\n")
        return 2
    return 1 if failures else 0


def main():
    command = [
        sys.executable,
        "-m",
        "pyright",
        "--outputjson",
        "--project",
        str(CONFIG),
        *checked_files(),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT, check=False)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        sys.stderr.write(f"error: could not run pyright: {error}\n")
        sys.exit(2)
    sys.exit(outcome(result))


if __name__ == "__main__":
    main()
