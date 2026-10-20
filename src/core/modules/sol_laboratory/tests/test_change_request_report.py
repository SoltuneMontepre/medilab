from odoo.exceptions import UserError
from odoo.tests import tagged

from .change_request_case import ChangeRequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK, MODEL_TEST_REPORT


@tagged("post_install", "-at_install")
class TestChangeRequestReport(ChangeRequestCase):
    def test_an_approved_change_request_on_an_issued_report_creates_a_new_version_the_portal_serves(self):
        portal = self.portal_user()
        self.complete()
        report = self.report()
        self.sign(report)
        request = self.raise_on(
            report,
            person=self.courier,
            change="Reissue the report with the customer's new registered name.",
            reason="The customer changed its business registration.",
        )

        self.sign(request)

        version = self.env[MODEL_TEST_REPORT].browse(request.new_document_id)
        self.assertEqual((report.status, version.status), ("replaced", "draft"))
        self.assertEqual((version.version, version.replaces_id), (2, report))
        self.assertIn(version, self.waiting_for("to_sign"))
        task = self.env[MODEL_TASK].search([("document_model", "=", version._name), ("document_id", "=", version.id)])
        self.assertEqual(task.note, request.requested_change)
        with self.assertRaises(UserError):
            self.raise_on(report, person=self.courier)

        self.sign(version)

        self.assertEqual(version.status, "issued")
        self.assertNotEqual(version.code, report.code)
        self.assertEqual(self.request.status, "reported")
        self.assertTrue(report.attachment_id)
        reports = self.env[MODEL_TEST_REPORT]
        self.assertEqual(reports.search(reports._portal_domain(portal)), version)
