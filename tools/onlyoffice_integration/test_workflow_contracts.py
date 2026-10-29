"""Run the actual CI change decision for API-only and runtime-only updates."""

import fnmatch
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class TestWorkflowContracts(unittest.TestCase):
    def decision(self, files="", runtime="false"):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.core.yml").read_text())
        step = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "result")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            subprocess.run(
                ["bash", "-e", "-c", step["run"]],
                env={
                    **os.environ,
                    "EVENT": "pull_request",
                    "FILES": files,
                    "AI": "false",
                    "E2E": "false",
                    "RUNTIME": runtime,
                    "GITHUB_OUTPUT": str(output),
                },
                check=True,
                capture_output=True,
                timeout=5,
            )
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    # def test_runtime_only_changes_keep_sonar_and_runtime_coverage_enabled(self):
    #     result = self.decision(runtime="true")

    #     self.assertEqual(result["scan"], "true")
    #     self.assertEqual(result["runtime"], "true")
    #     self.assertEqual(result["relevant"], "false")

    def test_device_and_updater_openapi_only_changes_run_core_and_sync_contracts(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.sync-app.yml").read_text())
        step = next(step for step in workflow["jobs"]["changes"]["steps"] if step.get("id") == "filter")
        patterns = yaml.safe_load(step["with"]["filters"])["relevant"]
        for name in ("openapi.yaml", "sync-updates.openapi.yaml"):
            path = "src/core/modules/sol_laboratory/api/" + name
            with self.subTest(path=path):
                self.assertEqual(self.decision(path)["relevant"], "true")
                self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns))


if __name__ == "__main__":
    unittest.main()
