"""Run the actual Task entrypoints with controlled native tools, without starting services."""

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
PREFIX = "LOCAL_SETUP_PROBE="


class LocalSetupTaskTests(unittest.TestCase):
    def invoke(self, arguments, *, program, body, dotenv_text="", environment=None):
        with tempfile.TemporaryDirectory(prefix="task setup ") as directory:
            root = Path(directory)
            probe = root / "probe.py"
            probe.write_text(body, encoding="utf-8")
            command = [sys.executable, str(probe)]
            if os.name == "nt":
                launcher = root / f"{program}.cmd"
                launcher.write_text(
                    "@echo off\n@" + subprocess.list2cmdline(command) + " %*\n",
                    encoding="utf-8",
                )
            else:
                launcher = root / program
                launcher.write_text(
                    "#!/bin/sh\nexec "
                    + " ".join(map(shlex.quote, command))
                    + ' "$@"\n',
                    encoding="utf-8",
                )
                launcher.chmod(0o755)
            dotenv = root / "selected.env"
            dotenv.write_text(dotenv_text, encoding="utf-8")
            env = os.environ.copy()
            for key in [
                "MODULES",
                "EXCLUDE",
                "MEDILAB_SETUP_MODULES",
                "FAKE_TASK_DOTENV_PROBE",
            ]:
                env.pop(key, None)
            env.update(environment or {})
            env.update(
                PATH=directory + os.pathsep + env.get("PATH", ""),
                MEDILAB_SETUP_DOTENV=str(dotenv),
                NO_COLOR="1",
            )
            return subprocess.run(
                [TASK, *arguments],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )

    def test_root_setup_forwards_modules_and_does_not_treat_exclude_as_upgrade_selection(
        self,
    ):
        body = """import json,os,sys
if sys.argv[1:2] == ['-c']:
    exec(sys.argv[2])
    raise SystemExit(0)
assert sys.argv[1:] == ['tools/scripts/local_setup.py', 'setup'], sys.argv
print('LOCAL_SETUP_PROBE='+json.dumps(os.environ['MEDILAB_SETUP_MODULES']))
raise SystemExit(73)
"""
        for arguments, expected in [
            (["setup"], "all"),
            (["setup", "MODULES=sol_laboratory"], "sol_laboratory"),
            (["setup", "EXCLUDE=sol_demo"], "all"),
        ]:
            with self.subTest(arguments=arguments):
                result = self.invoke(arguments, program="python", body=body)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exit status 73", result.stderr + result.stdout)
                observed = next(
                    line[len(PREFIX) :]
                    for line in result.stdout.splitlines()
                    if line.startswith(PREFIX)
                )
                self.assertEqual(json.loads(observed), expected)

    def test_missing_python_fails_before_orchestration_with_platform_guidance(self):
        body = "import sys; raise SystemExit(1 if sys.argv[1:2] == ['-c'] else 73)\n"
        result = self.invoke(["setup"], program="python", body=body)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Python 3.12+ is required", result.stdout + result.stderr)
        self.assertNotIn("exit status 73", result.stdout + result.stderr)

    def test_fresh_task_dotenv_override_is_honored_by_real_task(self):
        body = "import json,os; print('LOCAL_SETUP_PROBE='+json.dumps(os.environ.get('FAKE_TASK_DOTENV_PROBE')))\n"
        for dotenv_text, expected in [
            ("FAKE_TASK_DOTENV_PROBE=owned-placeholder\n", "owned-placeholder"),
            ("", None),
        ]:
            with self.subTest(expected=expected):
                result = self.invoke(
                    ["dev:sync"], program="uv", body=body, dotenv_text=dotenv_text
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                observed = next(
                    line[len(PREFIX) :]
                    for line in result.stdout.splitlines()
                    if line.startswith(PREFIX)
                )
                self.assertEqual(json.loads(observed), expected)


if __name__ == "__main__":
    unittest.main()
