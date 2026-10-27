"""Check browser-test onboarding and launch behavior through Task without opening Cypress."""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = shutil.which("task") or "task"
SCRIPT = (ROOT / "tools/scripts/test_e2e.sh").as_posix()
LOG = (ROOT / "tools/scripts/log.sh").as_posix()
TEST_URL = "http://localhost:18169"


class TestE2ETasks(unittest.TestCase):
    def run_mode(self, mode, *, health=0, cypress_status=0, browser="chrome", only=None):
        with tempfile.TemporaryDirectory() as directory:
            taskfile = Path(directory) / "Taskfile.yml"
            calls = Path(directory) / "calls.txt"
            taskfile.write_text(
                """version: "3"
tasks:
  launch:
    silent: true
    cmds:
      - |
        bun() {
          if [[ "$1" == --eval ]]; then
            return "$E2E_TEST_HEALTH"
          fi
          printf 'bun %s|%s|%s\\n' "$*" "$MEDILAB_URL" "${ELECTRON_RUN_AS_NODE-unset}" >> "$E2E_TEST_CALLS"
          if [[ "$1" == install ]]; then
            printf 'Checked dependencies (no changes).\\n'
          fi
          if [[ "$1" == run ]]; then
            return "$E2E_TEST_STATUS"
          fi
          return 0
        }
        bunx() {
          printf 'bunx %s|%s|%s\\n' "$*" "$MEDILAB_URL" "${ELECTRON_RUN_AS_NODE-unset}" >> "$E2E_TEST_CALLS"
          if [[ "$2" == open ]]; then
            return "$E2E_TEST_STATUS"
          fi
          return 0
        }
"""
                f"        . {shlex.quote(SCRIPT)} {shlex.quote(mode)} {shlex.quote(LOG)}\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                NO_COLOR="1",
                MEDILAB_URL="http://localhost:9999",
                MEDILAB_E2E_URL=TEST_URL,
                MEDILAB_TAP_BROWSER=browser,
                ELECTRON_RUN_AS_NODE="1",
                E2E_TEST_HEALTH=str(health),
                E2E_TEST_STATUS=str(cypress_status),
                E2E_TEST_CALLS=calls.as_posix(),
            )
            for key in ("MEDILAB_E2E_SPEC", "MEDILAB_E2E_GREP"):
                env.pop(key, None)
            env.update(only or {})
            result = subprocess.run(
                [TASK, "--taskfile", str(taskfile), "launch"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
                check=False,
            )
            return result, calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []

    def test_help_explains_setup_and_modes_without_installing_or_launching(self):
        result, calls = self.run_mode("help", health=1)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, [])
        for text in (TEST_URL, "task up", "task test:e2e:open", "E2E Testing", "MEDILAB_URL", "README.md"):
            self.assertIn(text, result.stdout)

    def test_run_restores_the_binary_even_when_dependencies_have_not_changed(self):
        result, calls = self.run_mode("run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no changes", result.stdout)
        self.assertEqual(
            calls,
            [
                f"bun install --frozen-lockfile --ignore-scripts|{TEST_URL}|unset",
                f"bunx cypress install|{TEST_URL}|unset",
                f"bun run test|{TEST_URL}|unset",
            ],
        )
        self.assertIn("Browser tests passed.", result.stdout)

    def test_run_passes_only_the_chosen_specs_and_tests_to_cypress(self):
        only = {"MEDILAB_E2E_SPEC": "cypress/e2e/login.cy.js", "MEDILAB_E2E_GREP": "TC-WF01-A5"}
        result, calls = self.run_mode("run", only=only)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1], f"bun run test --spec cypress/e2e/login.cy.js --expose grep=TC-WF01-A5|{TEST_URL}|unset")
        self.assertIn("Running only the tests whose title contains TC-WF01-A5.", result.stdout)

    def test_open_installs_the_binary_and_launches_the_app_with_the_selected_url(self):
        result, calls = self.run_mode("open")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-2:], [f"bunx cypress install|{TEST_URL}|unset", f"bunx cypress open|{TEST_URL}|unset"])
        self.assertIn("Choose E2E Testing", result.stdout)
        self.assertNotIn("Browser tests passed.", result.stdout)

    def test_tap_opens_e2e_with_a_supported_browser(self):
        result, calls = self.run_mode("tap")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[-1], f"bunx cypress open --e2e --browser chrome|{TEST_URL}|unset")
        self.assertIn("test:e2e:tap TAP_ARGS=", result.stdout)
        self.assertNotIn("Browser tests passed.", result.stdout)

    def test_tap_rejects_an_unsupported_browser_before_installing(self):
        result, calls = self.run_mode("tap", browser="firefox")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        self.assertIn("TAP_BROWSER", result.stdout + result.stderr)

    def test_stopped_odoo_explains_recovery_before_installing_or_launching(self):
        result, calls = self.run_mode("run", health=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])
        output = result.stdout + result.stderr
        for text in (TEST_URL, "task up", "task logs", "MEDILAB_URL", "task test:e2e:help"):
            self.assertIn(text, output)

    def test_cypress_failure_keeps_its_exit_status_and_never_reports_success(self):
        for mode in ("run", "open", "tap"):
            with self.subTest(mode=mode):
                result, _ = self.run_mode(mode, cypress_status=23)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exit status 23", result.stdout + result.stderr)
                self.assertNotIn("Browser tests passed.", result.stdout)

    def test_public_help_uses_the_command_line_url_override(self):
        result = subprocess.run(
            [TASK, "test:e2e:help", f"MEDILAB_URL={TEST_URL}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(TEST_URL, result.stdout)


if __name__ == "__main__":
    unittest.main()
