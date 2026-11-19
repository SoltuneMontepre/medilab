from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .report_case import PDF, ReportCase


@tagged("post_install", "-at_install")
class TestTestReportDelivery(ReportCase):
    def deliver(self, report, person=None):
        self.as_person(report, person or self.courier).action_record_delivery()

    def test_an_issued_report_waits_for_delivery_until_it_is_recorded_with_when_and_by_whom(self):
        self.complete()
        self.sign()
        report = self.report()
        self.assertIn(report, self.waiting_for("to_deliver"))

        self.deliver(report)

        self.assertTrue(report.delivered_at)
        self.assertEqual(report.delivered_by_id, self.courier)
        self.assertNotIn(report, self.waiting_for("to_deliver"))

    def test_a_report_not_issued_cannot_be_delivered(self):
        self.complete()

        with self.assertRaises(UserError):
            self.deliver(self.report())
        self.assertFalse(self.report().delivered_at)

    def test_recording_a_delivery_needs_the_deliver_permission(self):
        self.complete()
        self.sign()

        with self.assertRaises(AccessError):
            self.deliver(self.report(), self.lab_head)

    def test_a_report_delivered_by_email_is_emailed_to_its_recipient(self):
        recipient = self.env["res.partner"].create({"name": "Mai Thi Lan", "email": "lan.mai@anphu.example"})
        self.request.write({"delivery_method": "email", "report_recipient_id": recipient.id})
        self.complete()
        self.sign()
        report = self.report()

        self.deliver(report)

        message = self.delivery_messages(report)
        self.assertEqual(message.attachment_ids, report.attachment_id)
        self.assertEqual(bytes(message.attachment_ids.raw), PDF)
        self.assertEqual(message.notification_ids.res_partner_id, recipient)
        self.assertEqual(message.notification_ids.mail_mail_id.email_to, recipient.email)

    def test_a_report_handed_over_in_person_or_sent_by_post_is_recorded_without_an_email(self):
        self.request.write({"delivery_method": "in_person"})
        self.complete()
        self.sign()
        report = self.report()
        self.deliver(report)
        self.assertEqual((report.delivered_by_id, bool(report.delivered_at)), (self.courier, True))
        self.assertFalse(self.delivery_messages(report))

    def test_a_report_sent_by_post_is_recorded_without_an_email(self):
        recipient = self.env["res.partner"].create({"name": "Mai Thi Lan", "email": "lan.mai@anphu.example"})
        self.request.write(
            {"delivery_method": "post", "delivery_note": "12 Nguyen Hue", "report_recipient_id": recipient.id}
        )
        self.complete()
        self.sign()
        report = self.report()
        self.assertEqual(report.delivery_note, "12 Nguyen Hue")
        self.deliver(report)
        self.assertEqual((report.delivered_by_id, bool(report.delivered_at)), (self.courier, True))
        self.assertFalse(self.delivery_messages(report))

    def test_a_report_delivered_by_email_without_an_address_is_not_recorded(self):
        recipient = self.env["res.partner"].create({"name": "Mai Thi Lan"})
        self.request.write({"delivery_method": "email", "report_recipient_id": recipient.id})
        self.complete()
        self.sign()
        report = self.report()
        with self.assertRaises(UserError):
            self.deliver(report)
        self.assertFalse(report.delivered_at)

    def delivery_messages(self, report):
        return self.env["mail.message"].search(
            [
                ("model", "=", report._name),
                ("res_id", "=", report.id),
                ("subtype_id", "=", self.env.ref("sol_laboratory.event_test_report_delivered").id),
            ]
        )
