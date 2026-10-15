from odoo.tests import HttpCase, new_test_user, tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER


@tagged("post_install", "-at_install")
class TestTestReportPortal(HttpCase, ReportCase):
    """A customer's portal user downloads the issued reports of their own requests, and nothing else."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        contact = cls.env["res.partner"].create({"name": "Nguyen Thi Hoa", "parent_id": cls.customer.partner_id.id})
        cls.portal = new_test_user(cls.env, "hoa.portal", groups="base.group_portal", partner_id=contact.id)
        other = cls.env[MODEL_CUSTOMER].create({"name": "Green Farm Co., Ltd.", "is_company": True})
        new_test_user(cls.env, "farm.portal", groups="base.group_portal", partner_id=other.partner_id.id)

    def download(self, report):
        return self.url_open(f"/my/test-reports/{report.id}/download")

    def test_a_customer_downloads_their_issued_report(self):
        self.complete()
        self.sign()
        report = self.report()
        self.authenticate("hoa.portal", "hoa.portal")

        self.assertIn(report.code, self.url_open("/my/test-reports").text)
        response = self.download(report)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, bytes(report.attachment_id.raw))

    def test_a_report_not_issued_cannot_be_downloaded(self):
        self.complete()
        self.authenticate("hoa.portal", "hoa.portal")

        self.assertEqual(self.download(self.report()).status_code, 404)

    def test_a_customer_cannot_download_another_customers_report(self):
        self.complete()
        self.sign()
        report = self.report()
        self.authenticate("farm.portal", "farm.portal")

        self.assertNotIn(report.code, self.url_open("/my/test-reports").text)
        self.assertEqual(self.download(report).status_code, 404)
