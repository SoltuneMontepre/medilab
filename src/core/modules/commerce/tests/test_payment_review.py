import re
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .payos_case import PayosCase
from odoo.addons.commerce.constants.models import MODEL_PAYMENT
from odoo.addons.commerce.constants.xml_ids import REPORT_RECEIPT

RECEIPT_FORMAT = r"^\d{4} \d{2}/PT$"


@tagged("post_install", "-at_install")
class TestPaymentReview(PayosCase):
    def setUp(self):
        super().setUp()
        self.invoice = self.create_invoice(lines=((5_000_000, 0),))
        self.payment = self.pay(self.invoice, 2_000_000, user=self.salesperson)

    def as_accountant(self, records):
        return records.with_user(self.accountant.user_id)

    def test_sales_cannot_confirm_or_reject(self):
        self.payment.rejection_reason = "x"
        as_sales = self.payment.with_user(self.salesperson.user_id)
        for action in (as_sales.action_confirm, as_sales.action_reject):
            with self.subTest(action=action.__name__), self.assertRaises(AccessError):
                action()
        self.assertEqual(self.payment.status, "pending")

    def test_confirming_numbers_a_unique_receipt_that_renders(self):
        second = self.pay(self.invoice, 1_000_000, user=self.salesperson)

        self.as_accountant(self.payment).action_confirm()
        self.as_accountant(second).action_confirm()

        codes = [self.payment.receipt_code, second.receipt_code]
        self.assertTrue(all(re.match(RECEIPT_FORMAT, code) for code in codes), codes)
        self.assertNotEqual(*codes)
        self.assertEqual((self.payment.status, self.payment.reviewed_by_id), ("confirmed", self.accountant.user_id))
        self.assertEqual((self.invoice.amount_paid, self.invoice.amount_pending), (3_000_000, 0))
        html = self.env["ir.actions.report"]._render_qweb_html(REPORT_RECEIPT, self.payment.ids)[0].decode()
        self.assertIn(self.payment.receipt_code, html)
        self.assertIn("2.000.000", html.replace("\xa0", " ").replace("2,000,000", "2.000.000"))

    def test_a_rejection_needs_a_reason_restores_the_pending_amount_and_notifies(self):
        with self.assertRaisesRegex(UserError, "reason"):
            self.as_accountant(self.payment).action_reject()

        self.as_accountant(self.payment).write({"rejection_reason": "No transfer on the statement"})
        with patch.object(type(self.env[MODEL_PAYMENT]), "_notify_rejected", autospec=True) as notify:
            self.as_accountant(self.payment).action_reject()

        self.assertEqual((self.payment.status, self.payment.reviewed_by_id), ("rejected", self.accountant.user_id))
        self.assertEqual(
            (self.invoice.amount_pending, self.invoice.amount_paid, self.invoice.payment_status), (0, 0, "not_paid")
        )
        notify.assert_called_once()
        self.assertEqual(notify.call_args.args[0], self.payment)

    def test_a_reviewed_payment_is_frozen_and_only_a_pending_one_is_deleted(self):
        self.as_accountant(self.payment).action_confirm()

        for vals in ({"amount": 1}, {"payment_date": "2030-01-01"}, {"method": "cash"}):
            with self.subTest(vals=vals), self.assertRaisesRegex(UserError, "cannot be changed"):
                self.as_accountant(self.payment).write(vals)
        with self.assertRaisesRegex(UserError, "Only a pending payment"):
            self.as_accountant(self.payment).unlink()
        with self.assertRaisesRegex(UserError, "Only a pending payment"):
            self.as_accountant(self.payment).action_confirm()

        pending = self.pay(self.invoice, 500_000, user=self.salesperson)
        self.as_accountant(pending).write({"amount": 600_000})
        self.as_accountant(pending).unlink()
        self.assertFalse(pending.exists())

    def test_the_receipt_is_printed_for_a_confirmed_payment_only(self):
        with self.assertRaisesRegex(UserError, "confirmed payment only"):
            self.as_accountant(self.payment).action_print_receipt()
        self.as_accountant(self.payment).action_confirm()

        action = self.as_accountant(self.payment).action_print_receipt()

        self.assertEqual(action["report_name"], "commerce.report_receipt")
