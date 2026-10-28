import subprocess
import sys
import tempfile
import time

import requests

from odoo.tools import config

from .laboratory_bucket_case import closed_port
from .laboratory_http_process import odoo_command
from .scheduling_committed_case import PASSWORD, SchedulingCommittedCase


class SchedulingHttpCase(SchedulingCommittedCase):
    """Normal HTTP requests commit or roll back independently of Odoo's shared test cursor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server_log = cls.enterClassContext(tempfile.TemporaryFile(mode="w+b"))
        cls.http_url = f"http://127.0.0.1:{closed_port()}"
        coverage = sys.modules.get("coverage")
        tracing = coverage.Coverage.current() if coverage else None
        command = [
            *odoo_command(tracing),
            "-d",
            cls.registry.db_name,
            "--http-interface=127.0.0.1",
            f"--http-port={cls.http_url.rsplit(':', 1)[1]}",
            "--workers=0",
            "--max-cron-threads=0",
            "--log-level=warn",
        ]
        for option in ("db_host", "db_port", "db_user", "db_password", "data_dir", "addons_path"):
            if value := config[option]:
                command.extend(
                    [
                        "--" + option.replace("_", "-") if option in ("data_dir", "addons_path") else "--" + option,
                        ",".join(map(str, value)) if isinstance(value, (list, tuple)) else str(value),
                    ]
                )
        cls.http_server = subprocess.Popen(command, stdout=cls.server_log, stderr=subprocess.STDOUT)
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if cls.http_server.poll() is not None:
                cls.server_log.seek(0)
                raise AssertionError(cls.server_log.read().decode(errors="replace"))
            try:
                if requests.get(cls.http_url + "/web/health", timeout=1).status_code == 200:
                    return
            except (requests.ConnectionError, requests.Timeout):
                pass
            time.sleep(0.2)
        raise AssertionError("The scheduling HTTP worker did not start")

    @classmethod
    def stop_server(cls):
        cls.http_server.terminate()
        try:
            cls.http_server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.http_server.kill()
            cls.http_server.wait(timeout=10)

    def sign_in(self, number=0):
        browser = self.enterContext(requests.Session())
        response = browser.post(
            self.http_url + "/web/session/authenticate",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "db": self.registry.db_name,
                    "login": self.logins[number],
                    "password": PASSWORD,
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        self.assertEqual(response.json()["result"]["uid"], self.user_ids[number])
        return browser

    def call(self, browser, model, method, args):
        response = browser.post(
            f"{self.http_url}/web/dataset/call_kw/{model}/{method}",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": model,
                    "method": method,
                    "args": args,
                    "kwargs": {},
                },
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
