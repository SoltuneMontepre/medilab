import os

import jwt

from odoo.tests import tagged

from .editing_service import SECRET
from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    EDITING_UNAVAILABLE,
    JWT_SECRET_VARIABLE,
    NOT_EDITABLE,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION

DOCUMENT_URL = "https://bucket.lab.example/objects/0f1e2d3c?X-Amz-Signature=abc"
CALLBACK_URL = "https://lab.example/medilab/editing/callback/token"


@tagged("post_install", "-at_install")
class TestLaboratoryEditingAvailability(LaboratoryEditingCase):
    """Opening a file online asks the editing service first, and its editor configuration is signed."""

    def open(self, user, file=None):
        return self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(user)._open_for((file or self.file).with_user(user))

    def test_with_the_editing_service_down_opening_a_file_says_so_and_opens_nothing(self):
        self.health_check.return_value = False

        self.assertRefused(EDITING_UNAVAILABLE, self.open, self.tester)
        self.assertFalse(self.file.editing_session_ids)

    def test_with_the_editing_service_down_nobody_joins_an_open_session(self):
        session = self.open(self.tester)
        self.health_check.return_value = False

        self.assertRefused(EDITING_UNAVAILABLE, self.open, self.member)
        self.assertEqual(self.file.editing_session_ids, session)

    def test_without_the_secret_opening_a_file_says_the_editing_service_is_unavailable(self):
        os.environ.pop(JWT_SECRET_VARIABLE)

        self.assertRefused(EDITING_UNAVAILABLE, self.open, self.tester)

    def test_the_editing_service_is_asked_only_once_the_person_may_edit_the_file_online(self):
        self.health_check.return_value = False
        csv = self.file_of("2026/run-01.csv")
        self.save(csv, "run 1")

        self.assertRefused(NOT_FOUND, self.open, self.outsider)
        self.assertRefused(NOT_EDITABLE, self.open, self.tester, csv)
        self.health_check.assert_not_called()

    def test_the_editor_configuration_is_signed_with_force_save_off(self):
        session = self.open(self.tester)

        config = session._editor_config(self.tester, DOCUMENT_URL, CALLBACK_URL, 900)

        claims = jwt.decode(config.pop("token"), SECRET, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], 900)
        self.assertEqual({key: claims[key] for key in config}, config)
        self.assertEqual(
            config["document"],
            {
                "fileType": "xlsx",
                "key": session.sudo().document_key,
                "title": "Kết quả HPLC tháng 10.xlsx",
                "url": DOCUMENT_URL,
                "permissions": {"edit": True},
            },
        )
        self.assertEqual(config["documentType"], "cell")
        self.assertEqual(config["editorConfig"]["callbackUrl"], CALLBACK_URL)
        self.assertEqual(config["editorConfig"]["user"], {"id": str(self.tester.id), "name": self.tester.name})
        self.assertIs(config["editorConfig"]["customization"]["forcesave"], False)

    def test_each_office_document_opens_in_its_editor(self):
        for path, document_type in (("2026/Báo cáo.DOCX", "word"), ("2026/Trình bày.pptx", "slide")):
            with self.subTest(path=path):
                file = self.file_of(path)
                self.save(file, path)
                config = self.open(self.tester, file)._editor_config(self.tester, DOCUMENT_URL, CALLBACK_URL, 900)
                self.assertEqual(config["documentType"], document_type)

    def test_without_the_secret_no_editor_configuration_is_made(self):
        session = self.open(self.tester)
        os.environ.pop(JWT_SECRET_VARIABLE)

        self.assertRefused(EDITING_UNAVAILABLE, session._editor_config, self.tester, DOCUMENT_URL, CALLBACK_URL, 900)
