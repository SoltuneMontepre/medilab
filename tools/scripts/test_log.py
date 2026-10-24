"""Regression tests for the Task logging helpers."""

import importlib
import os
import queue
import re
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

pty = importlib.import_module("pty") if os.name == "posix" else None


ROOT = Path(__file__).resolve().parents[2]
LOG = (ROOT / "tools/scripts/log.sh").as_posix()
ODOO_LOG_STREAM = (ROOT / "tools/scripts/colorize_odoo_logs.py").as_posix()
ANSI = "\x1b["


class TaskLoggingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.taskfile = Path(cls.temp_dir.name) / "Taskfile.yml"
        cls.odoo_fixture = Path(cls.temp_dir.name) / "odoo_logs.py"
        cls.odoo_fixture.write_text(
            """import sys

print('2026-10-23 12:34:56,780 42 DEBUG ? odoo.modules.loading: Debug details')
print('2026-10-23 12:34:56,781 42 INFO ? odoo.modules.loading: Loaded modules')
print('2026-10-23 12:34:56,781 42 \x1b[1;32m\x1b[1;49mINFO\x1b[0m ? odoo.modules.loading: Native colored info')
print('2026-10-23 12:34:56,782 42 SUCCESS ? odoo.modules.loading: Setup finished')
print('2026-10-23 12:34:56,790 42 WARNING demo odoo.fields: Field ignored', file=sys.stderr)
print('2026-10-23 12:34:56,790 42 \x1b[1;33m\x1b[1;49mWARNING\x1b[0m demo odoo.fields: Native colored warning', file=sys.stderr)
print('2026-10-23 12:34:56,790 42 WARN demo odoo.fields: Deprecated field', file=sys.stderr)
print('2026-10-23 12:34:56,791 42 ERROR demo odoo.registry: Registry failed', file=sys.stderr)
print('2026-10-23 12:34:56,792 42 CRITICAL demo odoo.service: Startup failed', file=sys.stderr)
print('2026-10-23 12:34:56,793 42 FATAL demo odoo.service: Fatal startup failure', file=sys.stderr)
print('Traceback (most recent call last):', file=sys.stderr)
print('  File "/odoo/server.py", line 10, in start', file=sys.stderr)
print('ValueError: failed', file=sys.stderr)
print('ordinary INFO text', file=sys.stderr)
print('Plugin message contains ERROR but is not an Odoo record', file=sys.stderr)
""",
            encoding="utf-8",
        )
        cls.taskfile.write_text(
            f'''version: "3"
tasks:
  emit:
    silent: true
    cmds:
      - |
        . "{LOG}"
        log_step "Section"
        log_info "Info message"
        log_ok "Success message"
        log_warn "Warning message"
        log_error "Error message"
        log_debug "Debug message"
        log_link "Service" "https://example.test"
  prompt:
    silent: true
    cmds:
      - |
        . "{LOG}"
        log_prompt "Continue?"
        read -r answer
        printf 'answer=%s\\n' "$answer"
  status:
    silent: true
    cmds:
      - |
        . "{LOG}"
        if message=$(python -c "print('Compose project configured.')"); then
          log_info "$message"
        else
          status=$?
          log_error "Could not set the Compose project for this checkout."
          exit "$status"
        fi
  fail:
    silent: true
    cmds:
      - python -c "import sys; sys.exit(23)"
  fail_logged:
    silent: true
    cmds:
      - |
        . "{LOG}"
        if python -c "import sys; sys.exit(23)"; then
          exit 0
        else
          status=$?
          log_error "Odoo addon linking failed."
          exit "$status"
        fi
  odoo_logs:
    silent: true
    cmds:
      - |
        . "{LOG}"
        stdout_color=false
        stderr_color=false
        if log__color_enabled 1; then stdout_color=true; fi
        if log__color_enabled 2; then stderr_color=true; fi
        python "{ODOO_LOG_STREAM}" --stdout-color "$stdout_color" --stderr-color "$stderr_color" -- python "{cls.odoo_fixture}"
''',
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def run_task(self, task, env=None, **kwargs):
        task_env = os.environ.copy()
        for name in (
            "NO_COLOR",
            "FORCE_COLOR",
            "TERM",
            "WT_SESSION",
            "ANSICON",
            "ConEmuANSI",
        ):
            task_env.pop(name, None)
        task_env.update(env or {})
        return subprocess.run(
            ["task", "--taskfile", str(self.taskfile), "--force", task],
            cwd=ROOT,
            env=task_env,
            text=True,
            capture_output=True,
            check=False,
            **kwargs,
        )

    def test_redirected_output_is_plain_and_preserves_severity_streams(self):
        result = self.run_task("emit", env={"TERM": "xterm-256color"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)
        self.assertIn("[INFO] Info message", result.stdout)
        self.assertIn("[COMPLETED] Success message", result.stdout)
        self.assertIn("[WARNING] Warning message", result.stdout)
        self.assertIn("[DEBUG] Debug message", result.stdout)
        self.assertIn("https://example.test", result.stdout)
        self.assertIn("[ERROR] Error message", result.stderr)
        self.assertNotIn("[ERROR] Error message", result.stdout)

    def test_force_color_one_colors_only_labels_and_indicators(self):
        for level in ("1", "2", "3"):
            with self.subTest(force_color=level):
                result = self.run_task("emit", env={"FORCE_COLOR": level})

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"{ANSI}1;36m[INFO]{ANSI}0m Info message", result.stdout)
                self.assertIn(
                    f"{ANSI}1;32m[COMPLETED]{ANSI}0m Success message", result.stdout
                )
                self.assertIn(
                    f"{ANSI}1;33m[WARNING]{ANSI}0m Warning message", result.stdout
                )
                self.assertIn(f"{ANSI}2m[DEBUG]{ANSI}0m Debug message", result.stdout)
                self.assertIn(
                    f"{ANSI}1;31m[ERROR]{ANSI}0m Error message", result.stderr
                )
                self.assertIn(f"{ANSI}4;36mhttps://example.test{ANSI}0m", result.stdout)
                self.assertIn(f"{ANSI}1;36m{ANSI}1m==> Section", result.stdout)
                self.assertNotIn(f"{ANSI}1;36mInfo message", result.stdout)

    def test_no_color_takes_precedence_over_force_color(self):
        result = self.run_task("emit", env={"NO_COLOR": "1", "FORCE_COLOR": "1"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)

    def test_force_color_zero_disables_colors(self):
        result = self.run_task(
            "emit", env={"FORCE_COLOR": "0", "TERM": "xterm-256color"}
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)

    def test_invalid_force_color_falls_back_to_terminal_detection(self):
        result = self.run_task(
            "emit", env={"FORCE_COLOR": "invalid", "TERM": "xterm-256color"}
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)

    def test_dumb_terminal_does_not_receive_colors(self):
        result = self.run_task("emit", env={"TERM": "dumb"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)

    @unittest.skipUnless(
        os.name == "posix", "Pseudo-terminal stream checks require POSIX ptys."
    )
    def test_stdout_and_stderr_tty_capabilities_are_independent(self):
        for tty_stream, plain_stream in (("stdout", "stderr"), ("stderr", "stdout")):
            with self.subTest(tty_stream=tty_stream):
                master, slave = pty.openpty()
                kwargs = {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                }
                kwargs[tty_stream] = slave
                process = subprocess.Popen(
                    ["task", "--taskfile", str(self.taskfile), "--force", "emit"],
                    cwd=ROOT,
                    env=self._terminal_env(),
                    **kwargs,
                )
                os.close(slave)
                try:
                    stdout, stderr = process.communicate(timeout=10)
                    tty_chunks = []
                    while True:
                        ready, _, _ = select.select([master], [], [], 0.1)
                        if not ready:
                            break
                        try:
                            tty_chunks.append(os.read(master, 65536))
                        except OSError:
                            break
                    tty_output = b"".join(tty_chunks).decode(errors="replace")
                finally:
                    os.close(master)
                output = {
                    "stdout": (stdout or b"").decode(errors="replace"),
                    "stderr": (stderr or b"").decode(errors="replace"),
                }
                output[tty_stream] = tty_output

                self.assertEqual(process.returncode, 0, output["stderr"])
                self.assertIn(ANSI, output[tty_stream])
                self.assertNotIn(ANSI, output[plain_stream])

    @unittest.skipUnless(
        os.name == "posix", "Pseudo-terminal override checks require POSIX ptys."
    )
    def test_color_disabling_overrides_win_on_a_tty(self):
        overrides = ({"FORCE_COLOR": "0"}, {"NO_COLOR": "1", "FORCE_COLOR": "1"})
        for override in overrides:
            with self.subTest(override=override):
                master, slave = pty.openpty()
                process = subprocess.Popen(
                    ["task", "--taskfile", str(self.taskfile), "--force", "emit"],
                    cwd=ROOT,
                    env=self._terminal_env(**override),
                    stdin=subprocess.DEVNULL,
                    stdout=slave,
                    stderr=subprocess.PIPE,
                )
                os.close(slave)
                try:
                    _, stderr = process.communicate(timeout=10)
                    output = bytearray()
                    while True:
                        ready, _, _ = select.select([master], [], [], 0.1)
                        if not ready:
                            break
                        try:
                            output.extend(os.read(master, 65536))
                        except OSError:
                            break
                finally:
                    os.close(master)

                self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
                self.assertNotIn(ANSI, output.decode(errors="replace"))

    @unittest.skipUnless(
        os.name == "posix", "Pseudo-terminal capability checks require POSIX ptys."
    )
    def test_invalid_force_color_and_dumb_term_use_capability_fallback(self):
        cases = (({"FORCE_COLOR": "invalid"}, True), ({"TERM": "dumb"}, False))
        for overrides, expect_color in cases:
            with self.subTest(overrides=overrides):
                master, slave = pty.openpty()
                process = subprocess.Popen(
                    ["task", "--taskfile", str(self.taskfile), "--force", "emit"],
                    cwd=ROOT,
                    env=self._terminal_env(**overrides),
                    stdin=subprocess.DEVNULL,
                    stdout=slave,
                    stderr=subprocess.PIPE,
                )
                os.close(slave)
                try:
                    _, stderr = process.communicate(timeout=10)
                    output = bytearray()
                    while True:
                        ready, _, _ = select.select([master], [], [], 0.1)
                        if not ready:
                            break
                        try:
                            output.extend(os.read(master, 65536))
                        except OSError:
                            break
                finally:
                    os.close(master)

                self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
                self.assertEqual(ANSI in output.decode(errors="replace"), expect_color)

    @unittest.skipUnless(
        os.name == "posix", "Interactive pseudo-terminal checks require POSIX ptys."
    )
    def test_interactive_prompt_accepts_input_without_adding_a_newline(self):
        master, slave = pty.openpty()
        process = subprocess.Popen(
            ["task", "--taskfile", str(self.taskfile), "--force", "prompt"],
            cwd=ROOT,
            env=self._terminal_env(FORCE_COLOR="1"),
            stdin=slave,
            stdout=slave,
            stderr=subprocess.PIPE,
        )
        os.close(slave)
        captured = bytearray()
        try:
            deadline = time.monotonic() + 10
            while b"Continue? " not in captured and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        captured.extend(os.read(master, 4096))
                    except OSError:
                        break
                if process.poll() is not None:
                    break
            prompt = captured.decode(errors="replace")
            self.assertIn("Continue? ", prompt)
            self.assertNotIn("\n", prompt)
            os.write(master, b"yes\n")
            deadline = time.monotonic() + 10
            while process.poll() is None and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        captured.extend(os.read(master, 4096))
                    except OSError:
                        break
            if process.poll() is None:
                process.kill()
            _, stderr = process.communicate(timeout=1)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

        output = captured.decode(errors="replace")
        self.assertEqual(process.returncode, 0, stderr.decode(errors="replace"))
        self.assertIn("answer=yes", output)
        self.assertIn(ANSI, output)

    def test_task_reports_a_failing_subprocess_status(self):
        result = self.run_task("fail")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exit status 23", result.stderr)

    def test_python_status_output_can_be_formatted_by_the_shared_logger(self):
        result = self.run_task("status")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[INFO] Compose project configured.", result.stdout)

    def test_odoo_presenter_auto_mode_respects_force_color_precedence(self):
        for environment, expect_color in (
            ({"FORCE_COLOR": "1"}, True),
            ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, False),
        ):
            with self.subTest(environment=environment):
                process_env = os.environ.copy()
                for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
                    process_env.pop(name, None)
                process_env.update(environment)
                result = subprocess.run(
                    [
                        sys.executable,
                        ODOO_LOG_STREAM,
                        "--stdout-color",
                        "auto",
                        "--stderr-color",
                        "auto",
                        "--",
                        sys.executable,
                        str(self.odoo_fixture),
                    ],
                    cwd=ROOT,
                    env=process_env,
                    capture_output=True,
                    check=False,
                )

                self.assertEqual(result.returncode, 0, result.stderr.decode())
                has_color = ANSI.encode() in result.stdout + result.stderr
                self.assertEqual(has_color, expect_color)

    def test_native_odoo_color_is_normalized_to_requested_terminal_palette(self):
        result = self.run_task("odoo_logs", env={"FORCE_COLOR": "1"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            f"{ANSI}1;36mINFO{ANSI}0m ? odoo.modules.loading: Native colored info",
            result.stdout,
        )
        self.assertIn(
            f"{ANSI}1;33mWARNING{ANSI}0m demo odoo.fields: Native colored warning",
            result.stderr,
        )
        self.assertNotIn(f"{ANSI}1;32m{ANSI}1;49mINFO", result.stdout)

    def test_native_odoo_color_is_removed_when_no_color_is_set(self):
        result = self.run_task("odoo_logs", env={"NO_COLOR": "1", "FORCE_COLOR": "1"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)
        self.assertIn("INFO ? odoo.modules.loading: Native colored info", result.stdout)
        self.assertIn("WARNING demo odoo.fields: Native colored warning", result.stderr)

    def test_logged_subprocess_failure_keeps_the_task_failure_and_stderr_label(self):
        result = self.run_task("fail_logged")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[ERROR] Odoo addon linking failed.", result.stderr)
        self.assertIn("exit status 23", result.stderr)

    @unittest.skipUnless(
        os.name == "posix", "Live terminal presentation checks require POSIX ptys."
    )
    def test_odoo_severity_labels_color_on_the_live_terminal_and_tracebacks_stay_plain(
        self,
    ):
        master, slave = pty.openpty()
        process = subprocess.Popen(
            ["task", "--taskfile", str(self.taskfile), "--force", "odoo_logs"],
            cwd=ROOT,
            env=self._terminal_env(FORCE_COLOR="1"),
            stdin=subprocess.DEVNULL,
            stdout=slave,
            stderr=slave,
        )
        os.close(slave)
        try:
            output = bytearray()
            deadline = time.monotonic() + 10
            while process.poll() is None and time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        break
            if process.poll() is None:
                process.kill()
            process.wait(timeout=1)
        finally:
            os.close(master)

        rendered = output.decode(errors="replace")
        self.assertEqual(process.returncode, 0, rendered)
        self.assertIn(f"{ANSI}1;36mINFO{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}2;90mDEBUG{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;32mSUCCESS{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;33mWARNING{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;33mWARN{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;31mERROR{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;31mCRITICAL{ANSI}0m", rendered)
        self.assertIn(f"{ANSI}1;31mFATAL{ANSI}0m", rendered)
        self.assertIn("Traceback (most recent call last):", rendered)
        self.assertIn('File "/odoo/server.py"', rendered)
        self.assertIn("ValueError: failed", rendered)
        self.assertNotIn(f"{ANSI}1;31mTraceback", rendered)
        ordinary = rendered[
            rendered.index("Plugin message contains ERROR but is not an Odoo record") :
        ]
        self.assertNotIn(ANSI, ordinary.splitlines()[0])

    @unittest.skipUnless(
        os.name == "posix", "Per-stream terminal checks require POSIX ptys."
    )
    def test_odoo_presenter_detects_stdout_and_stderr_terminals_independently(self):
        for tty_stream, redirected_stream in (
            ("stdout", "stderr"),
            ("stderr", "stdout"),
        ):
            with self.subTest(tty_stream=tty_stream):
                master, slave = pty.openpty()
                kwargs = {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.PIPE,
                    "stderr": subprocess.PIPE,
                }
                kwargs[tty_stream] = slave
                process = subprocess.Popen(
                    ["task", "--taskfile", str(self.taskfile), "--force", "odoo_logs"],
                    cwd=ROOT,
                    env=self._terminal_env(),
                    **kwargs,
                )
                os.close(slave)
                try:
                    stdout, stderr = process.communicate(timeout=10)
                    tty_output = bytearray()
                    while True:
                        ready, _, _ = select.select([master], [], [], 0.1)
                        if not ready:
                            break
                        try:
                            tty_output.extend(os.read(master, 4096))
                        except OSError:
                            break
                finally:
                    os.close(master)
                redirected = {
                    "stdout": (stdout or b"").decode(errors="replace"),
                    "stderr": (stderr or b"").decode(errors="replace"),
                }
                redirected[tty_stream] = tty_output.decode(errors="replace")

                self.assertEqual(process.returncode, 0, redirected["stderr"])
                self.assertIn(ANSI, redirected[tty_stream])
                self.assertNotIn(ANSI, redirected[redirected_stream])

    def test_odoo_logs_stay_plain_when_redirected_and_keep_their_streams(self):
        result = self.run_task("odoo_logs", env={"TERM": "xterm-256color"})

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(ANSI, result.stdout + result.stderr)
        self.assertIn("INFO ? odoo.modules.loading", result.stdout)
        self.assertIn("WARNING demo odoo.fields", result.stderr)
        self.assertIn("ERROR demo odoo.registry", result.stderr)
        self.assertIn("Traceback (most recent call last):", result.stderr)
        self.assertIn("ordinary INFO text", result.stderr)
        self.assertNotIn(ANSI, result.stderr)

    def test_odoo_stream_wrapper_preserves_complete_lines_without_buffering_them(self):
        producer = (
            "import os, time\n"
            "os.write(1, b'2026-10-23 12:34:56,780 42 INFO demo odoo.registry: first\\n')\n"
            "time.sleep(1.0)\n"
            "os.write(1, b'2026-10-23 12:34:56,781 42 INFO demo odoo.registry: ' + b'x' * 10000 + b'\\n')\n"
            "os.write(2, b'2026-10-23 12:34:56,782 42 WARNING demo odoo.registry: warning\\n')\n"
            "os.write(2, b'Traceback (most recent call last):\\n  File \\\"/odoo/server.py\\\", line 10\\nValueError: failed\\n')\n"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                ODOO_LOG_STREAM,
                "--stdout-color",
                "true",
                "--stderr-color",
                "true",
                "--",
                sys.executable,
                "-c",
                producer,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIsNotNone(process.stdout)
        first_line = queue.Queue()
        threading.Thread(
            target=lambda: first_line.put(process.stdout.readline()), daemon=True
        ).start()
        try:
            first = first_line.get(timeout=0.5)
        except queue.Empty:
            process.kill()
            process.communicate(timeout=5)
            self.fail("the first complete Odoo line was buffered until process exit")
        self.assertIn(b"first", first)
        remaining_stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        strip_ansi = lambda stream: re.sub(rb"\x1b\[[0-9;]*m", b"", stream)
        stdout = strip_ansi(first + remaining_stdout)
        stderr = strip_ansi(stderr)
        self.assertEqual(stdout.count(b"INFO demo odoo.registry:"), 2)
        self.assertEqual(stdout.count(b"x"), 10000)
        self.assertEqual(stderr.count(b"WARNING demo odoo.registry:"), 1)
        self.assertEqual(stderr.count(b"Traceback (most recent call last):"), 1)
        self.assertIn(b'File "/odoo/server.py", line 10\nValueError: failed\n', stderr)

    def test_numeric_interactive_prompt_is_forwarded_before_child_exits(self):
        producer = "import os, time; os.write(1, b'1) Continue? '); time.sleep(1)"
        process = subprocess.Popen(
            [
                sys.executable,
                ODOO_LOG_STREAM,
                "--stdout-color",
                "false",
                "--stderr-color",
                "false",
                "--",
                sys.executable,
                "-c",
                producer,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            self.assertIsNotNone(process.stdout)
            prompt = queue.Queue()
            threading.Thread(
                target=lambda: prompt.put(process.stdout.read(13)), daemon=True
            ).start()
            try:
                first = prompt.get(timeout=0.5)
            except queue.Empty:
                self.fail("a numeric prompt was buffered until child exit")
            self.assertEqual(first, b"1) Continue? ")
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_odoo_stream_wrapper_preserves_subprocess_failure_code(self):
        result = subprocess.run(
            [
                sys.executable,
                ODOO_LOG_STREAM,
                "--stdout-color",
                "true",
                "--stderr-color",
                "false",
                "--",
                sys.executable,
                "-c",
                "import sys; sys.exit(23)",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 23, result.stderr)

    @unittest.skipUnless(os.name == "posix", "Signal exit codes use POSIX conventions.")
    def test_odoo_stream_wrapper_preserves_shell_signal_exit_code(self):
        result = subprocess.run(
            [
                sys.executable,
                ODOO_LOG_STREAM,
                "--stdout-color",
                "false",
                "--stderr-color",
                "false",
                "--",
                sys.executable,
                "-c",
                "import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 128 + signal.SIGTERM)

    def test_odoo_color_precedence_uses_shared_stream_detection(self):
        cases = (
            ({"FORCE_COLOR": "1"}, True),
            ({"FORCE_COLOR": "0"}, False),
            ({"NO_COLOR": "1", "FORCE_COLOR": "1"}, False),
        )
        for env, should_color in cases:
            with self.subTest(env=env):
                result = self.run_task("odoo_logs", env=env)

                self.assertEqual(result.returncode, 0, result.stderr)
                colored = ANSI in result.stdout + result.stderr
                self.assertEqual(colored, should_color)

    @staticmethod
    def _terminal_env(**overrides):
        env = os.environ.copy()
        for name in (
            "NO_COLOR",
            "FORCE_COLOR",
            "TERM",
            "WT_SESSION",
            "ANSICON",
            "ConEmuANSI",
        ):
            env.pop(name, None)
        env["TERM"] = "xterm-256color"
        env.update(overrides)
        return env


if __name__ == "__main__":
    unittest.main()
