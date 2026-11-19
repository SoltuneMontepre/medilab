import os
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .report_preparation_case import ReportPreparationCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PUBLIC_ADDRESS_VARIABLE
from odoo.addons.sol_laboratory.services.laboratory_editor_page import CALLBACK_ORIGIN_VARIABLE


@tagged("post_install", "-at_install")
class TestReportEditorPage(HttpCase, ReportPreparationCase):
    """Report templates open in the online editor page with their own permissions, never with a folder membership. A
    report's draft never opens in it: MediLab generates the draft and nobody edits it."""

    def setUp(self):
        super().setUp()
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    CALLBACK_ORIGIN_VARIABLE: "https://odoo.lab.example",
                    PUBLIC_ADDRESS_VARIABLE: "https://bucket.lab.example",
                },
            )
        )
        self.run_preparation()
        self.draft = self.report()

    def page(self, person, file):
        # The password of each person is their login.
        person.user_id.sudo().password = person.user_id.login
        self.authenticate(person.user_id.login, person.user_id.login)
        return self.url_open(f"/medilab/laboratory-files/{file.id}/edit", allow_redirects=False)

    def test_nobody_opens_a_report_draft_in_the_editor(self):
        for person in (self.courier, self.lab_head, self.template_admin):
            with self.subTest(person=person.name):
                response = self.page(person, self.draft.draft_file_id)
                self.assertEqual(response.status_code, 403)

    def test_template_draft_opens_for_its_administrator_only(self):
        template = self.new_template("vi", "Phiếu kết quả")
        self.assertEqual(self.page(self.template_admin, template.file_id).status_code, 200)
        self.assertEqual(self.page(self.courier, template.file_id).status_code, 403)
        self.assertEqual(self.page(self.template_admin, self.template.file_id).status_code, 409)

    def test_issued_report_downloads_while_onlyoffice_is_down(self):
        self.sign(self.draft)
        self.health_check.return_value = False
        portal = self.portal_user()
        self.authenticate(portal.login, portal.login)
        response = self.url_open(f"/my/test-reports/{self.draft.id}/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
