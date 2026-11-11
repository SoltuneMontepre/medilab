"""Classify native test output without persisting raw service logs."""

import ast
import json
import re


class NativeResults:
    def __init__(self):
        self.started = set()
        self.failed = set()
        self.summaries = []

    def observe(self, snapshot):
        messages = snapshot.stdout + snapshot.stderr
        self.started.update(re.findall(r"Starting (Test\w+\.test_\w+)", messages))
        self.failed.update(re.findall(r"(?:FAIL|ERROR|Failed): (?:[\w.]+\.)?(Test\w+\.test_\w+)", messages))
        for summary in re.findall(r"odoo.tests.result: ([^\n]+)", messages):
            if summary not in self.summaries:
                self.summaries.append(summary)

    def successful_summary(self):
        return bool(self.summaries and self.summaries[-1].startswith("0 failed, 0 error(s)"))

    def status(self, name, code):
        if name in self.failed:
            return "FAIL"
        if self.successful_summary() and code == 0:
            return "PASS"
        return "BLOCKED"

    def statuses(self, code):
        return {name: self.status(name, code) for name in sorted(self.started)}


def expected_test_names(source, native_only, selected):
    names = sorted(
        node.name
        for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )
    if native_only:
        names = []
    if selected:
        requested = set(selected.split(","))
        names = [name for name in names if name in requested]
        if len(names) != len(requested):
            raise ValueError("The selected real-service test does not exist.")
    return names


def callback_outcomes(result, files, expected_names, successful_summary):
    logs = result.stdout + result.stderr
    failed = set(re.findall(r"(?:FAIL|ERROR|Failed): (?:[\w.]+\.)?TestOnlyofficeReal\.(test_\w+)", logs))
    started = sorted(set(re.findall(r"Starting TestOnlyofficeReal\.(test_\w+)", logs)))
    outcomes = {path.stem: json.loads(path.read_text()).get("test_body_passed") for path in files}
    failed.update(name for name, outcome in outcomes.items() if outcome is False)
    return {
        "failed_tests": sorted(failed),
        "passed_tests": sorted(
            name for name, outcome in outcomes.items() if name not in failed and (outcome is True or successful_summary)
        ),
        "unknown_outcome_tests": sorted(
            name
            for name, outcome in outcomes.items()
            if name not in failed and outcome is None and not successful_summary
        ),
        "blocked_tests": [name for name in started if name not in outcomes and name not in failed],
        "not_started_tests": [name for name in expected_names if name not in started and name not in outcomes],
    }
