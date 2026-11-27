from odoo.tests import tagged

from .report_preparation_case import ReportPreparationCase

PREPARED_EVENT = "sol_laboratory.event_test_report_prepared"


@tagged("post_install", "-at_install")
class TestTestReportPrepared(ReportPreparationCase):
    """The people who sign a report are told when its PDF is prepared for their review."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lab_head.user_id.notification_type = "inbox"

    def messages(self, report):
        return self.env["mail.message"].search(
            [
                ("model", "=", report._name),
                ("res_id", "=", report.id),
                ("subtype_id", "=", self.env.ref(PREPARED_EVENT).id),
            ],
            order="id",
        )

    def test_the_lab_head_is_told_once_the_job_prepares_the_pdf(self):
        report = self.report()
        self.assertFalse(self.messages(report))

        self.run_preparation()

        candidate = report._candidate()
        message = self.messages(report)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.notification_key, f"test_report:{report.id}:{candidate.id}:prepared")
        self.assertIn(self.lab_head.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertNotIn(self.tester.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertIn(candidate.report_number, message.body or "")

    def test_running_the_job_again_without_a_change_tells_nobody_again(self):
        self.run_preparation()
        self.run_preparation()

        self.assertEqual(len(self.messages(self.report())), 1)

    def test_a_pdf_prepared_again_after_the_records_changed_tells_the_lab_head_again(self):
        self.run_preparation()
        self.customer.partner_id.name = "Công ty Nước Sạch Mới"

        self.run_preparation()

        messages = self.messages(self.report())
        self.assertEqual(len(messages), 2)
        self.assertIn(self.lab_head.user_id.partner_id, messages[-1].notification_ids.res_partner_id)

    def test_a_lab_head_who_prepares_the_pdf_again_is_not_told(self):
        self.run_preparation()
        report = self.report()

        self.as_person(report, self.lab_head).action_prepare_pdf()

        messages = self.messages(report)
        self.assertEqual(len(messages), 2)
        self.assertNotIn(self.lab_head.user_id.partner_id, messages[-1].notification_ids.res_partner_id)
