import os
from unittest.mock import patch

import requests

from odoo.tests import BaseCase, tagged

from .editing_service import LocalEditingService
from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE
from odoo.addons.sol_laboratory.services.editing_service_health import HEALTH_PATH, is_editing_service_up


@tagged("post_install", "-at_install")
class TestEditingServiceHealth(BaseCase):
    def setUp(self):
        super().setUp()
        self.service = LocalEditingService(self)
        environment = patch.dict(os.environ, {INTERNAL_URL_VARIABLE: self.service.url})
        environment.start()
        self.addCleanup(environment.stop)

    def test_the_editing_service_is_up_when_its_health_check_answers_true(self):
        self.service.answer(HEALTH_PATH, b"true")

        self.assertTrue(is_editing_service_up())
        self.assertEqual(self.service.asked, [HEALTH_PATH])

    def test_any_other_answer_is_down(self):
        for status, body in ((200, b"false"), (200, b""), (500, b"true"), (404, b"")):
            with self.subTest(status=status, body=body):
                self.service.answer(HEALTH_PATH, body, status=status)
                self.assertFalse(is_editing_service_up())

    def test_a_redirect_is_not_followed(self):
        self.service.answer(HEALTH_PATH, status=302, headers={"Location": "/elsewhere"})
        self.service.answer("/elsewhere", b"true")

        self.assertFalse(is_editing_service_up())
        self.assertNotIn("/elsewhere", self.service.asked)

    def test_an_editing_service_that_does_not_answer_is_down(self):
        for error in (requests.ConnectionError(), requests.Timeout()):
            with self.subTest(error=type(error).__name__), patch.object(requests, "get", side_effect=error):
                self.assertFalse(is_editing_service_up())

    def test_without_its_address_the_editing_service_is_down(self):
        self.service.answer(HEALTH_PATH, b"true")
        os.environ.pop(INTERNAL_URL_VARIABLE)

        self.assertFalse(is_editing_service_up())
        self.assertEqual(self.service.asked, [])
