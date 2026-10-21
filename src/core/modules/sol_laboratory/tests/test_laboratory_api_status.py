import os
import socket
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP


def closed_port():
    """A port of this machine nothing listens on, as the address of an editing service that is down."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@tagged("post_install", "-at_install")
class TestLaboratoryApiStatus(LaboratoryApiCase):
    def add_check(self, check):
        checks = type(self.env[MODEL_IR_HTTP])._laboratory_files_ready_checks

        def with_check(http):
            return {**checks(http), "bucket": check}

        self.patch(type(self.env[MODEL_IR_HTTP]), "_laboratory_files_ready_checks", with_check)

    def test_health_answers_once_odoo_serves_requests(self):
        response = self.api("GET", "/health")

        self.assertEqual(response.json(), {"status": "pass"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_ready_checks_the_database_and_answers_ready_while_the_editing_service_is_down(self):
        with patch.dict(os.environ, {INTERNAL_URL_VARIABLE: f"http://127.0.0.1:{closed_port()}"}):
            response = self.api("GET", "/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "pass", "checks": {"database": "pass"}})

    def test_ready_fails_when_a_check_fails_or_breaks(self):
        def broken():
            raise ConnectionError("The bucket does not answer.")

        for check in (lambda: False, broken):
            with self.subTest(check=check), mute_logger("odoo.addons.sol_laboratory.controllers.laboratory_api_status"):
                self.add_check(check)
                response = self.api("GET", "/ready")

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"status": "fail", "checks": {"database": "pass", "bucket": "fail"}})
