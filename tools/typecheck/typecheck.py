"""Check all module sources and tests; fail on any error, warning, or incomplete run."""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from artifacts import validate

ROOT = Path(__file__).resolve().parents[2]
TYPING = ROOT / ".local/typecheck/current"
CONFIG = TYPING / "pyrightconfig.json"
SEVERITY_COUNTS = {
    "error": "errorCount",
    "warning": "warningCount",
    "information": "informationCount",
}
SUMMARY_COUNTS = ("filesAnalyzed", *SEVERITY_COUNTS.values())


def fails(diagnostic):
    return diagnostic["severity"] in ("error", "warning")


def describe(diagnostic):
    start = diagnostic["range"]["start"]
    rule = f" ({diagnostic['rule']})" if diagnostic.get("rule") else ""
    return f"{diagnostic['file']}:{start['line'] + 1}:{start['character'] + 1} - {diagnostic['severity']}: {diagnostic['message']}{rule}"


def checked_files():
    """The files given as arguments, as absolute paths, so pyright never reads one as an option."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir", type=Path, help="save the raw report and diagnostic counts"
    )
    parser.add_argument(
        "files", nargs="*", type=Path, help="files to check instead of the modules"
    )
    args = parser.parse_args()
    files = [path.resolve() for path in args.files]
    if missing := [str(path) for path in files if not path.is_file()]:
        parser.error(f"not a file: {', '.join(missing)}")
    return [str(path) for path in files], args.report_dir


def save_report(result, directory):
    """Preserve Pyright output even when it is malformed or the process failed."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyright.json").write_text(result.stdout, encoding="utf-8")
    (directory / "pyright.stderr.txt").write_text(result.stderr, encoding="utf-8")
    report = read_report(result.stdout)
    counts = {"exitCode": result.returncode, "complete": report is not None}
    if report is not None:
        diagnostics = report["generalDiagnostics"]
        counts["summary"] = report["summary"]
        for group in ("rule", "module", "file", "severity"):
            values = []
            for diagnostic in diagnostics:
                path = Path(diagnostic["file"])
                try:
                    relative = path.relative_to(ROOT / "src/core/modules")
                    module = relative.parts[0]
                except ValueError:
                    module = "<outside modules>"
                values.append(
                    {"module": module, "file": str(path)}.get(
                        group, diagnostic.get(group, "<none>")
                    )
                )
            counts[group] = dict(sorted(Counter(values).items()))
    (directory / "counts.json").write_text(
        json.dumps(counts, indent=2) + "\n", encoding="utf-8"
    )


def is_complete(diagnostic):
    if not isinstance(diagnostic, dict):
        return False
    if not all(
        isinstance(diagnostic[key], str) for key in ("file", "severity", "message")
    ):
        return False
    if not diagnostic["file"] or diagnostic["severity"] not in SEVERITY_COUNTS:
        return False
    if "rule" in diagnostic and not isinstance(diagnostic["rule"], str):
        return False
    start, end = diagnostic["range"]["start"], diagnostic["range"]["end"]
    return all(
        type(position[key]) is int and position[key] >= 0
        for position in (start, end)
        for key in ("line", "character")
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
            and all(
                type(report["summary"][key]) is int and report["summary"][key] >= 0
                for key in SUMMARY_COUNTS
            )
            and all(
                is_complete(diagnostic) for diagnostic in report["generalDiagnostics"]
            )
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
    errors = sum(
        diagnostic["severity"] == "error" for diagnostic in report["generalDiagnostics"]
    )
    if errors != summary["errorCount"] or (returncode == 1) != (errors > 0):
        return f"pyright exited with {returncode} and counted {summary['errorCount']} errors, but listed {errors}."
    for severity, count in SEVERITY_COUNTS.items():
        if (
            sum(
                diagnostic["severity"] == severity
                for diagnostic in report["generalDiagnostics"]
            )
            != summary[count]
        ):
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
        failures = [
            diagnostic
            for diagnostic in report["generalDiagnostics"]
            if fails(diagnostic)
        ]
        for diagnostic in failures:
            sys.stdout.write(describe(diagnostic) + "\n")
        summary = report["summary"]
        sys.stdout.write(
            f"{summary['errorCount']} errors, {summary['warningCount']} warnings in {summary['filesAnalyzed']} files\n"
        )
    if problem := broken_run(result.returncode, report):
        sys.stderr.write(f"error: {problem}\n")
        return 2
    return 1 if failures else 0


def main():
    files, report_directory = checked_files()
    try:
        validate(ROOT, TYPING)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.stderr.write(
            f"error: typing is not ready: {error}. Run task typecheck:prepare.\n"
        )
        sys.exit(2)
    command = [
        sys.executable,
        "-m",
        "pyright",
        "--outputjson",
        "--project",
        str(CONFIG),
        *files,
    ]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, cwd=ROOT, check=False
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        sys.stderr.write(f"error: could not run pyright: {error}\n")
        sys.exit(2)
    if report_directory is not None:
        try:
            save_report(result, report_directory)
        except OSError as error:
            sys.stderr.write(f"error: could not save pyright report: {error}\n")
            sys.exit(2)
    code = outcome(result)
    try:
        validate(ROOT, TYPING)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.stderr.write(f"error: typing inputs changed during analysis: {error}\n")
        sys.exit(2)
    sys.exit(code)


if __name__ == "__main__":
    main()
