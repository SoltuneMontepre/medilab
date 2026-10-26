"""Check module selection through the repository's real Task entrypoint without running containers."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = shutil.which("task") or "task"
PROBE_PREFIX = "TASKFILE_MODULE_SELECTION="


class TaskfileModulesTests(unittest.TestCase):
    def run_task(self, task, *variables, dry=True, overrides=None):
        env = os.environ.copy()
        for name in ("MODULES", "EXCLUDE", "TASK_SILENT", "TASK_VERBOSE"):
            env.pop(name, None)
        env["NO_COLOR"] = "1"
        env.update(overrides or {})
        result = subprocess.run(
            [TASK, "--verbose", *(["--dry"] if dry else []), task, *variables],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        return result

    def dry_run(self, task, *variables):
        result = self.run_task(task, *variables)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        return output

    def core_selection(self, *variables):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory) / "probe.py"
            probe.write_text(
                "import json, os, sys\n"
                f"print({PROBE_PREFIX!r} + json.dumps("
                "{key: os.environ[key] for key in ('MODULES', 'TEST_MODULES', 'TAGS')}))\n"
                "sys.exit(73)\n",
                encoding="utf-8",
            )
            if os.name == "nt":
                shim = Path(directory) / "python.cmd"
                command = subprocess.list2cmdline([sys.executable, str(probe)])
                shim.write_text(f"@echo off\n@{command}\n", encoding="utf-8")
            else:
                shim = Path(directory) / "python"
                command = " ".join(
                    shlex.quote(part) for part in (sys.executable, str(probe))
                )
                shim.write_text(f"#!/bin/sh\nexec {command}\n", encoding="utf-8")
                shim.chmod(0o755)
            result = self.run_task(
                "test:core",
                *variables,
                dry=False,
                overrides={"PATH": directory + os.pathsep + os.environ["PATH"]},
            )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        selection = next(
            (
                line.removeprefix(PROBE_PREFIX)
                for line in result.stdout.splitlines()
                if line.startswith(PROBE_PREFIX)
            ),
            None,
        )
        self.assertIsNotNone(selection, output)
        self.assertIn("exit status 73", output)
        return json.loads(selection)

    def assert_core_selection(self, selection, modules, tests=None):
        tests = modules if tests is None else tests
        self.assertEqual(selection["MODULES"], ",".join(modules))
        self.assertEqual(selection["TEST_MODULES"], ",".join(tests))
        self.assertEqual(selection["TAGS"], ",".join(f"/{module}" for module in tests))

    def all_modules(self):
        return [
            name
            for line in (ROOT / "src/core/modules.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if (name := line.strip()) and name != "base"
        ]

    def assert_upgrade_modules(self, output, modules):
        self.assertIn(
            f'python tools/scripts/local_compose.py guard-demo-install "{modules}"',
            output,
        )
        self.assertIn(f'if [ "{modules}" = "all" ]; then', output)

    def test_upgrade_defaults_to_installed_modules(self):
        self.assert_upgrade_modules(self.dry_run("upgrade"), "all")

    def test_setup_defaults_to_installed_modules(self):
        self.assert_upgrade_modules(self.dry_run("setup"), "all")

    def test_upgrade_keeps_explicit_module_selection(self):
        self.assert_upgrade_modules(
            self.dry_run("upgrade", "MODULES=sol_laboratory"), "sol_laboratory"
        )

    def test_upgrade_keeps_explicit_demo_install_guard(self):
        modules = "sol_laboratory,sol_demo"
        self.assert_upgrade_modules(
            self.dry_run("upgrade", f"MODULES={modules}"), modules
        )

    def test_test_exclusion_does_not_select_upgrade_modules(self):
        self.assert_upgrade_modules(self.dry_run("upgrade", "EXCLUDE=sol_demo"), "all")

    def test_core_defaults_to_every_application_module(self):
        self.assert_core_selection(self.core_selection(), self.all_modules())

    def test_core_keeps_module_exclusion(self):
        modules = [name for name in self.all_modules() if name != "sol_demo"]
        self.assert_core_selection(self.core_selection("EXCLUDE=sol_demo"), modules)

    def test_core_keeps_explicit_install_selection(self):
        self.assert_core_selection(
            self.core_selection("MODULES=sol_laboratory"), ["sol_laboratory"]
        )

    def test_core_can_test_one_module_while_installing_all(self):
        self.assert_core_selection(
            self.core_selection("TEST_MODULES=sol_laboratory"),
            self.all_modules(),
            ["sol_laboratory"],
        )


if __name__ == "__main__":
    unittest.main()
