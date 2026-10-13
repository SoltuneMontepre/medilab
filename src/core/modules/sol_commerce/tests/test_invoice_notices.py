from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from odoo.tests import tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE


@tagged("post_install", "-at_install")
class TestInvoiceNotices(InvoicingCase):
    def test_emailing_an_invoice_does_not_change_what_is_owed(self):
        self.partner.email = "an@example.com"
        invoice = self.order.create_advance_invoice()
        owed = invoice.amount_owed
        state = invoice.payment_state
        with patch(
            "odoo.addons.base.models.ir_actions_report.IrActionsReport._render_qweb_pdf",
            return_value=(b"%PDF", "pdf"),
        ):
            first = invoice.action_send_invoice()
            second = invoice.action_send_invoice()
        self.assertEqual(first, second)
        self.assertEqual(invoice.payment_state, state)
        self.assertEqual(invoice.amount_owed, owed)
        self.assertTrue(first.attachment_ids)

    def test_an_overdue_invoice_is_reminded_once_per_vietnam_day(self):
        self.partner.email = "an@example.com"
        invoice = self.order.create_advance_invoice()
        today = datetime.now(ZoneInfo(VIETNAM_ZONE)).date()
        invoice.invoice_date_due = today - timedelta(days=1)
        self.assertTrue(invoice.is_overdue)
        self.env["medilab.scheduled.job"]._run_key("overdue.reminders")
        self.env["medilab.scheduled.job"]._run_key("overdue.reminders")
        messages = self.env["mail.message"].search(
            [("notification_key", "=", f"invoice:{invoice.id}:overdue:{today.isoformat()}")]
        )
        self.assertEqual(len(messages), 1)

    def test_confirming_and_rejecting_queue_a_notice_and_keep_the_activity(self):
        self.partner.email = "an@example.com"
        invoice = self.order.create_advance_invoice()
        confirmed = self.env["account.payment"].create_pending_payment(invoice, 100_000, "cash")
        confirmed.action_post()
        receipt = self.env["mail.message"].search([("notification_key", "=", f"payment:{confirmed.id}:receipt")])
        self.assertEqual(invoice.payment_state != "not_paid", True)
        self.assertTrue(receipt)
        rejected = self.env["account.payment"].create_pending_payment(invoice, 100_000, "cash")
        rejected.rejection_reason = "Missing transfer"
        rejected.action_reject_payment()
        activity = self.env["mail.activity"].search([("res_model", "=", rejected._name), ("res_id", "=", rejected.id)])
        notice = self.env["mail.message"].search([("notification_key", "=", f"payment:{rejected.id}:rejected")])
        self.assertTrue(activity)
        self.assertTrue(notice)
        self.assertEqual(invoice.amount_residual, invoice.amount_total - 100_000)
