import os
import urllib.parse

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
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_FILE_URL_MINUTES,
    LABORATORY_FILE_URL_PARAMETER,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

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

        config = session._editor_config(self.tester, CALLBACK_URL)

        claims = jwt.decode(config.pop("token"), SECRET, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], DEFAULT_LABORATORY_FILE_URL_MINUTES * 60)
        self.assertEqual({key: claims[key] for key in config}, config)
        document = dict(config["document"])
        address = urllib.parse.urlsplit(document.pop("url"))
        self.assertEqual(
            document,
            {
                "fileType": "xlsx",
                "key": session.sudo().document_key,
                "title": "Kết quả HPLC tháng 10.xlsx",
                "permissions": {"edit": True},
            },
        )
        self.assertBaseVersionAddress(address, session, DEFAULT_LABORATORY_FILE_URL_MINUTES * 60)
        self.assertEqual(config["documentType"], "cell")
        self.assertEqual(config["editorConfig"]["callbackUrl"], CALLBACK_URL)
        self.assertEqual(config["editorConfig"]["user"], {"id": str(self.tester.id), "name": self.tester.name})
        self.assertIs(config["editorConfig"]["customization"]["forcesave"], False)

    def test_each_office_document_opens_in_its_editor(self):
        for path, document_type in (("2026/Báo cáo.DOCX", "word"), ("2026/Trình bày.pptx", "slide")):
            with self.subTest(path=path):
                file = self.file_of(path)
                self.save(file, path)
                config = self.open(self.tester, file)._editor_config(self.tester, CALLBACK_URL)
                self.assertEqual(config["documentType"], document_type)

    def test_without_the_secret_no_editor_configuration_is_made(self):
        session = self.open(self.tester)
        os.environ.pop(JWT_SECRET_VARIABLE)

        self.assertRefused(EDITING_UNAVAILABLE, session._editor_config, self.tester, CALLBACK_URL)

    def test_the_editor_reads_the_base_version_for_as_long_as_the_settings_say(self):
        self.env["ir.config_parameter"].set_int(LABORATORY_FILE_URL_PARAMETER, 30)
        session = self.open(self.tester)

        config = session._editor_config(self.tester, CALLBACK_URL)

        claims = jwt.decode(config["token"], SECRET, algorithms=["HS256"])
        self.assertEqual(claims["exp"] - claims["iat"], 1800)
        self.assertBaseVersionAddress(urllib.parse.urlsplit(config["document"]["url"]), session, 1800)

    def assertBaseVersionAddress(self, address, session, seconds):
        """The address is a presigned read of the object of the session's base version, on the bucket's public
        address, for seconds."""
        bucket = laboratory_bucket.settings()
        if bucket is None:
            self.fail("The laboratory files bucket is not configured.")
        query = urllib.parse.parse_qs(address.query)
        key = session.sudo().base_version_id.content_id.object_key
        self.assertEqual(address.netloc, urllib.parse.urlsplit(bucket.public_address).netloc)
        self.assertEqual(address.path, f"/{bucket.name}/{key}")
        self.assertEqual(query["X-Amz-Expires"], [str(seconds)])
        self.assertIn("attachment", query["response-content-disposition"][0])
