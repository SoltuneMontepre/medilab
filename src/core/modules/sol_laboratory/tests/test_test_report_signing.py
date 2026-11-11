from datetime import timedelta

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .report_case import ReportCase
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_LEVEL, MODEL_TASK
from odoo.addons.sol_laboratory.constants.xml_ids import TEST_REPORT_REPORT
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestTestReportSigning(ReportCase):
    def html(self, report):
        return self.env["ir.actions.report"]._render_qweb_html(TEST_REPORT_REPORT, report.ids)[0].decode()

    def test_print_samples_uses_odoo_20_union_api(self):
        second_test = self.add_test()
        results = (self.enter(), self.enter(test=second_test))
        for result in results:
            self.send(result)
            self.approve(result)
        report = self.report()

        with self.assertNoLogs("py.warnings", level="WARNING"):
            samples = report._print_samples()

        self.assertEqual(len(samples), 1)
        self.assertEqual(len(samples[0]["rows"]), 2)

    def test_signing_issues_the_report_with_a_number_and_a_pdf_in_the_requests_language(self):
        self.customer.email = "qa@anphu.example"
        self.request.report_language = "en"
        self.complete()
        report = self.report()

        self.sign(report)

        self.assertEqual(report.status, "issued")
        self.assertTrue(assert_instance(report.code, str).startswith("PKQ."))
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

    def name_levels_in_vietnamese(self):
        for level in self.env[MODEL_APPROVAL_LEVEL].search([]):
            level.with_context(lang="vi_VN").name = f"VI {level.name}"

    def test_a_bilingual_report_prints_the_approvers_levels_in_vietnamese_and_english(self):
        self.name_levels_in_vietnamese()
        self.complete()
        self.sign()

        report = self.report()
        self.assertIn("VI Lab head / Lab head", self.html(report))
        # The heads who approved the results print their level in both languages too.
        levels = [signer["level"] for signer in report._print_signers()]
        self.assertGreater(len(levels), 1)
        self.assertTrue(all(level.startswith("VI ") and " / " in level for level in levels), levels)

    def test_a_vietnamese_report_prints_the_approvers_levels_in_vietnamese(self):
        self.name_levels_in_vietnamese()
        self.request.report_language = "vi"
        self.complete()
        self.sign()

        report = self.report()

        self.assertIn("VI Lab head", self.html(report))
        levels = [signer["level"] for signer in report._print_signers()]
        self.assertGreater(len(levels), 1)
        self.assertTrue(all(level.startswith("VI ") and " / " not in level for level in levels), levels)

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

    def test_a_report_with_a_result_the_head_approved_themself_waits_for_the_lab_head(self):
        result = self.enter(person=self.head)
        self.send(result, self.head)
        self.approve(result)
        report = self.report()

        self.assertEqual(report.status, "draft")
        self.assertFalse(report.code)
        self.sign(report)

        self.assertEqual(report.status, "issued")
        self.assertEqual([signer["name"] for signer in report._print_signers()], [self.head.name, self.lab_head.name])

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

    def test_the_pdf_of_an_issued_report_cannot_be_replaced(self):
        self.complete()
        self.sign()

        with self.assertRaises(UserError):
            self.as_person(self.report().attachment_id, self.courier).write({"raw": b"forged"})

    def test_a_draft_report_is_printed_only_by_those_who_read_results(self):
        self.complete()
        report = self.report()

        def print_as(person):
            printing = self.as_person(self.env["ir.actions.report"], person)
            return printing._render_qweb_html(TEST_REPORT_REPORT, report.ids)[0].decode()

        with self.assertRaises(AccessError):
            print_as(self.courier)
        self.assertIn(self.parameter.name, print_as(self.lab_head))
        self.sign(report)
        self.assertIn(self.parameter.name, print_as(self.courier))

    def test_issuing_the_report_retains_a_kept_sample_from_the_report_date(self):
        self.sample_type.write({"is_retained": True, "retention_days": 30})
        self.complete()

        self.sign()

        self.assertEqual(self.sample.status, "retained")
        self.assertEqual(self.sample.retained_until, self.report()._report_day() + timedelta(days=30))
