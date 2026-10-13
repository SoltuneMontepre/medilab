"""Run pyright on the modules and fail on its errors and on imports of names that do not exist.

pyright reports "from <module> import <name>" of a missing name under reportAttributeAccessIssue, the rule that
pyrightconfig.json lowers to a warning for Odoo's dynamic models. This script reports those warnings as errors.
Files given as arguments are checked instead of the modules.
"""

import ast
import functools
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "pyrightconfig.json"
IMPORT_NAME_RULE = "reportAttributeAccessIssue"


@functools.cache
def import_lines(path):
    """The line numbers, from 0 as pyright counts them, of the "from ... import" statements in the file at path."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)
    return {
        line
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for line in range(node.lineno - 1, node.end_lineno or node.lineno)
    }


def fails(diagnostic):
    if diagnostic["severity"] == "error":
        return True
    line = diagnostic["range"]["start"]["line"]
    return diagnostic.get("rule") == IMPORT_NAME_RULE and line in import_lines(diagnostic["file"])


def describe(diagnostic):
    start = diagnostic["range"]["start"]
    rule = f" ({diagnostic['rule']})" if diagnostic.get("rule") else ""
    return f"{diagnostic['file']}:{start['line'] + 1}:{start['character'] + 1} - error: {diagnostic['message']}{rule}"


def main():
    command = [sys.executable, "-m", "pyright", "--outputjson", "--project", str(CONFIG), *sys.argv[1:]]
    result = subprocess.run(command, capture_output=True, text=True, cwd=ROOT)
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(result.stdout + result.stderr)
        sys.exit(result.returncode or 1)
    failures = [diagnostic for diagnostic in report["generalDiagnostics"] if fails(diagnostic)]
    for diagnostic in failures:
        sys.stdout.write(describe(diagnostic) + "\n")
    summary = report["summary"]
    warnings = summary["warningCount"] - (len(failures) - summary["errorCount"])
    sys.stdout.write(f"{len(failures)} errors, {warnings} warnings in {summary['filesAnalyzed']} files\n")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
