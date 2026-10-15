from odoo.exceptions import UserError
from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE, MODEL_TASK

REASON = "Lead reads 0.008 mg/L against 0.002 last month; check the digestion blank."


@tagged("post_install", "-at_install")
class TestTestReportRejection(ReportCase):
    def reject(self, results, reason=REASON):
        self.as_person(self.report(), self.lab_head).action_reject(reason, results)

    def test_rejecting_without_a_reason_or_a_result_is_refused(self):
        result = self.complete()

        for reason, results in (("", result), (REASON, result.browse())):
            with self.subTest(reason=reason), self.assertRaises(UserError):
                self.reject(results, reason)

        self.assertEqual((self.report().status, result.status), ("draft", "approved"))

    def test_rejecting_sends_the_named_results_back_unassigned_and_unsigned_until_approved_again(self):
        arsenic = self.add_test()
        lead = self.complete()
        kept = self.complete(test=arsenic)

        self.reject(lead)

        report = self.report()
        self.assertEqual((lead.status, self.test.status), ("none", "testing"))
        self.assertEqual((self.sample.status, self.request.status), ("testing", "testing"))
        self.assertEqual(kept.status, "approved")
        signatures = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", lead._name), ("document_id", "=", lead.id), ("withdrawn_at", "=", False)]
        )
        self.assertFalse(signatures)
        task = self.test._testing_task()
        self.assertEqual((task.status, task.department_id), ("open", self.department))
        self.assertFalse(task.assignee_id)
        self.assertIn(REASON, task.note)
        self.assertEqual(report.status, "draft")
        self.assertNotIn(report, self.waiting_for("to_sign"))
        self.assertFalse(self.as_person(report, self.lab_head).approval_can_sign)

        task.write({"assignee_id": self.tester.id, "status": "assigned"})
        self.send(lead)
        self.approve(lead)

        self.assertEqual(self.request.status, "completed")
        self.assertIn(report, self.waiting_for("to_sign"))
        signing = self.env[MODEL_TASK].search(
            [("document_model", "=", report._name), ("document_id", "=", report.id), ("status", "=", "open")]
        )
        self.assertEqual(signing.action, "sign")
        self.sign(report)
        self.assertEqual(report.status, "issued")
