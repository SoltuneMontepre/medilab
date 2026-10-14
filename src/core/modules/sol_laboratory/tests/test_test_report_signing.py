from odoo.exceptions import UserError
from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT


@tagged("post_install", "-at_install")
class TestTestReportSigning(ReportCase):
    def html(self, report):
        return self.env["ir.actions.report"]._render_qweb_html(TEST_REPORT_REPORT, report.ids)[0].decode()

    def test_signing_issues_the_report_with_a_number_and_a_pdf_in_the_requests_language(self):
        self.customer.email = "qa@anphu.example"
        self.request.report_language = "en"
        self.complete()
        report = self.report()

        self.sign(report)

        self.assertEqual(report.status, "issued")
        self.assertTrue(report.code.startswith("PKQ."))
        self.assertTrue(report.issued_at)
        self.assertEqual(report.attachment_id.name, f"{report.code}.pdf")
        self.assertEqual((self.request.status, self.sample.status), ("reported", "reported"))
        task = self.env[MODEL_TASK].search([("document_model", "=", report._name), ("document_id", "=", report.id)])
        self.assertEqual(task.status, "done")
        printed = self.html(report)
        self.assertIn("Parameter", printed)
        self.assertNotIn("Chỉ Tiêu", printed)
        message = self.env["mail.message"].search([("model", "=", report._name), ("res_id", "=", report.id)])
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_test_report_issued"))
        self.assertEqual(message.notification_ids.res_partner_id, self.customer.partner_id)

    def test_a_bilingual_report_prints_vietnamese_and_english_side_by_side(self):
        self.complete()
        self.sign()

        printed = self.html(self.report())

        self.assertIn("Chỉ Tiêu / Parameter", printed)

    def test_the_report_prints_the_heads_and_the_lab_head_not_the_testers_and_leaves_out_cancelled_tests(self):
        arsenic = self.add_test()
        self.as_person(arsenic, self.head).action_cancel("The sample is too small for arsenic.")
        self.complete()
        self.sign()

        printed = self.html(self.report())

        self.assertIn(self.head.name, printed)
        self.assertIn(self.lab_head.name, printed)
        self.assertNotIn(self.tester.name, printed)
        self.assertIn(self.parameter.name, printed)
        self.assertNotIn(arsenic.parameter_id.name, printed)

    def test_only_the_lab_head_signs_and_an_issued_report_is_locked(self):
        self.complete()
        report = self.report()
        self.assertFalse(self.as_person(report, self.courier).approval_can_sign)
        self.sign(report)

        for action in (self.sign, lambda report: self.as_person(report, self.lab_head).action_withdraw()):
            with self.subTest(action=action), self.assertRaises(UserError):
                action(report)
        with self.assertRaises(UserError):
            self.as_person(report, self.courier).write({"language": "vi"})
