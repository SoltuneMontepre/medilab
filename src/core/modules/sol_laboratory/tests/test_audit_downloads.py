from odoo.tests import HttpCase, tagged

from .audit_case import AuditLookup
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT


@tagged("post_install", "-at_install")
class TestAuditDownloads(AuditLookup, RequestCase, HttpCase):
    def setUp(self):
        super().setUp()
        self.report = self.env.ref(SAMPLE_LABEL_REPORT)
        self.authenticate("admin", "admin")

    def test_downloading_a_printed_report_is_recorded_on_its_documents(self):
        self.url_open(f"/report/pdf/{self.report.report_name}/{self.sample.id}")

        entry = self.entries(self.sample, "download")
        self.assertEqual(entry.note, self.report.name)
        self.assertEqual((entry.source, entry.user_id.login), ("screen", "admin"))

    def test_a_printed_report_shown_in_the_browser_is_not_a_download(self):
        self.url_open(f"/report/html/{self.report.report_name}/{self.sample.id}")

        self.assertFalse(self.entries(self.sample, "download"))

    def test_downloading_a_file_of_a_document_is_recorded_on_the_file(self):
        photo = self.env[MODEL_IR_ATTACHMENT].create(
            {"name": "bottle.jpg", "raw": b"photo", "res_model": self.sample._name, "res_id": self.sample.id}
        )

        self.url_open(f"/web/content/{photo.id}")
        self.assertFalse(self.entries(photo, "download"))
        self.url_open(f"/web/content/{photo.id}?download=true")

        self.assertEqual(self.entries(photo, "download").note, "bottle.jpg")
