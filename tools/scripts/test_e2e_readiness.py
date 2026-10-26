"""Run the E2E app's real readiness step against a local HTTP fixture, without installing modules."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = shutil.which("task") or "task"


class TestE2EReadiness(unittest.TestCase):
    def test_ready_odoo_succeeds_without_writing_a_null_device_file(self):
        for trailing_slash in (False, True):
            with self.subTest(trailing_slash=trailing_slash):
                result = self.check_response(200, trailing_slash=trailing_slash)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("Odoo is ready", result.stdout)
                self.assertNotIn("curl: (23)", result.stderr)

    def test_unhealthy_odoo_fails_with_the_server_log_command(self):
        result = self.check_response(503)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("task logs", result.stdout + result.stderr)
        self.assertNotIn("Odoo is ready", result.stdout)

    def check_response(self, status, *, trailing_slash=False):
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(status if self.path == "/web/health" else 404)
                self.end_headers()
                self.wfile.write(b'{"status": "pass"}')

            def log_message(self, *_args):
                return

        with ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}" + ("/" if trailing_slash else "")
                return self.run_readiness(url)
            finally:
                server.shutdown()
                thread.join()

    def run_readiness(self, url):
        task_source = (ROOT / "tools/taskfiles/test.taskfile.yml").read_text(encoding="utf-8")
        app = task_source.split("  test:e2e:app:\n", 1)[1].split("\n  test:apps:", 1)[0]
        readiness = textwrap.dedent(app.rsplit("      - |\n", 1)[1]).strip()
        with tempfile.TemporaryDirectory() as directory:
            taskfile = Path(directory) / "Taskfile.yml"
            taskfile.write_text(
                'version: "3"\nvars:\n'
                f'  LOG: "{(ROOT / "tools/scripts/log.sh").as_posix()}"\n'
                f'  E2E_URL: "{url}"\n'
                "  E2E_HEALTH_RETRIES: 0\n"
                "  E2E_HEALTH_DELAY: 0\n"
                "tasks:\n  readiness:\n    silent: true\n"
                f'    dir: "{ROOT.as_posix()}"\n'
                "    cmds:\n      - |\n" + textwrap.indent(readiness, "        ") + "\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env.update(
                NO_COLOR="1",
                MEDILAB_E2E_URL=url,
                MEDILAB_E2E_HEALTH_RETRIES="0",
                MEDILAB_E2E_HEALTH_DELAY="0",
                PATH=str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", ""),
            )
            return subprocess.run(
                [TASK, "--taskfile", str(taskfile), "readiness"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
                check=False,
            )


if __name__ == "__main__":
    unittest.main()
