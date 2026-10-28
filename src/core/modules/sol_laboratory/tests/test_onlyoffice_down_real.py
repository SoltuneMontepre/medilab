"""Opt-in HTTP refusal/readiness acceptance while the owned Document Server is actually stopped."""

import json
import os
import socket
import uuid
from pathlib import Path
from unittest import SkipTest

import requests

from odoo.tests import tagged

from . import test_laboratory_editor_http, test_onlyoffice_real
from .laboratory_editing_http_case import LaboratoryEditingHttpCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PUBLIC_ADDRESS_VARIABLE
from odoo.addons.sol_laboratory.services.laboratory_editor_page import CALLBACK_ORIGIN_VARIABLE


@tagged("post_install", "-at_install", "-standard", "onlyoffice_down_real")
class TestOnlyofficeDownReal(LaboratoryEditingHttpCase):
    HTTP_INTERFACE = "0.0.0.0"

    @classmethod
    def setUpClass(cls):
        if os.environ.get("ONLYOFFICE_PAGE_DOWN") != "1":
            raise SkipTest("Explicitly stop only the owned Document Server before this acceptance case.")
        super().setUpClass()

    @classmethod
    def editing_internal_url(cls):
        return "http://documentserver"

    @classmethod
    def editing_public_url(cls):
        return "http://localhost:8081"

    @classmethod
    def server_environment(cls):
        port = cls.http_url.rsplit(":", 1)[1]
        return {
            CALLBACK_ORIGIN_VARIABLE: f"http://{socket.gethostname()}:{port}",
            PUBLIC_ADDRESS_VARIABLE: "http://localhost:3900",
        }

    def setUp(self):
        self.marker = "MEDILAB_DOWN_" + uuid.uuid4().hex
        self.extension = "docx"
        super().setUp()
        self.path = f"/medilab/laboratory-files/{self.file_id}/edit"

    prepare = test_onlyoffice_real.TestOnlyofficeReal.prepare

    def prepare_session(self, env):
        return 0, "", "", env.ref("base.user_admin").id

    def test_stopped_service_refuses_page_without_affecting_readiness(self):
        try:
            health = requests.get(self.editing_internal_url() + "/healthcheck", timeout=5)
        except requests.RequestException:
            healthy = False
        else:
            healthy = health.status_code == 200 and health.text.strip() == "true"
        self.assertFalse(healthy)
        client = test_laboratory_editor_http.TestLaboratoryEditorHttp.login(self)
        page = client.get(self.http_url + self.path, timeout=30)
        self.assertEqual(page.status_code, 503)
        self.assertIn("Online editing is unavailable", page.text)
        self.assertFalse(self.committed(lambda env: bool(self.session(env))))
        ready = requests.get(self.http_url + "/medilab/api/v1/ready", timeout=15)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()["status"], "pass")
        self.assertEqual(self.committed(lambda env: len(self.file(env).version_ids)), 1)
        directory = Path(os.environ["ONLYOFFICE_EVIDENCE_DIR"])
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        (directory / "service-down.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "editor_http": 503,
                    "ready_http": 200,
                    "ready": ready.json(),
                    "session_created": False,
                    "version_count": 1,
                },
                indent=2,
            )
            + "\n"
        )
