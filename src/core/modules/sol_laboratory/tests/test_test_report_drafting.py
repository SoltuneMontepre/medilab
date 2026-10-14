from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK


@tagged("post_install", "-at_install")
class TestTestReportDrafting(ReportCase):
    def test_a_request_whose_results_are_not_all_approved_has_no_report_waiting(self):
        arsenic = self.add_test()
        self.complete()
        self.send(self.enter(test=arsenic))

        self.assertEqual(self.request.status, "awaiting_approval")
        self.assertFalse(self.report())
        self.assertNotIn(self.request, self.waiting_for("to_sign").request_id)

    def test_approving_the_last_result_drafts_the_report_and_the_lab_heads_signing_task(self):
        arsenic = self.add_test()
        self.as_person(arsenic, self.head).action_cancel("The sample is too small for arsenic.")
        self.request.report_language = "en"

        self.complete()

        report = self.report()
        self.assertEqual((report.status, report.language, report.version), ("draft", "en", 1))
        self.assertFalse(report.code)
        self.assertIn(report, self.waiting_for("to_sign"))
        task = self.env[MODEL_TASK].search([("document_model", "=", report._name), ("document_id", "=", report.id)])
        self.assertEqual((task.type_id.code, task.action, task.status), ("report_signing", "sign", "open"))
        self.assertTrue(self.as_person(report, self.lab_head).approval_can_sign)
