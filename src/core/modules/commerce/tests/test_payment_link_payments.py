from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .payos_case import GET_PATH, PayosCase, link_data, signed_answer, transaction
from odoo.addons.commerce.constants.payos import JOB_CALLS, JOB_POLL


@tagged("post_install", "-at_install")
class TestPaymentLinkPayments(PayosCase):
    def test_a_full_transfer_records_one_confirmed_online_payment(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, _ = self.create_link(invoice)

        self.notify(link, 5_000_000, "FT1")
        self.notify(link, 5_000_000, "FT1")

        payment = link.payment_ids
        self.assertEqual(len(payment), 1)
        self.assertEqual(
            (payment.status, payment.method, payment.amount, payment.recorded_by_id),
            ("confirmed", "online", 5_000_000, self.env["res.users"]),
        )
        self.assertEqual((payment.payment_link_id, link.transaction_ids.payment_id), (link, payment))
        self.assertEqual(payment.payment_date.isoformat(), "2026-05-11")
        self.assertTrue(payment.receipt_code)
        self.assertEqual((invoice.payment_status, invoice.amount_owed, link.status), ("paid", 0, "paid"))

    def test_an_underpaid_link_records_each_transfer_and_the_sum_matches(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, fake = self.create_link(invoice)

        self.notify(link, 2_000_000, "FT1")

        self.assertEqual((link.status, link.match_status, len(link.payment_ids)), ("pending", "underpaid", 1))
        self.assertEqual((invoice.payment_status, invoice.amount_owed), ("partially_paid", 3_000_000))

        fake.answers[GET_PATH] = signed_answer(
            link_data(
                link, "PAID", [transaction("FT1", 2_000_000), transaction("FT2", 3_000_000, "2026-03-04 09:00:00")]
            )
        )
        self.run_job(JOB_POLL)
        self.run_job(JOB_POLL)

        self.assertEqual((link.status, link.match_status, len(link.payment_ids)), ("paid", "matched", 2))
        self.assertEqual(sum(link.payment_ids.mapped("amount")), link.amount_paid)
        self.assertEqual(link.amount_paid, link.amount)
        self.assertEqual((invoice.payment_status, invoice.amount_owed), ("paid", 0))
        self.assertEqual(len(link.transaction_ids), 2)

    def test_a_late_online_payment_after_a_manual_settlement_is_recorded_as_overpaying(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        link, fake = self.create_link(invoice)
        fake.answers = {}
        self.pay(invoice, 5_000_000)

        self.notify(link, 5_000_000, "FT1")

        online = link.payment_ids
        self.assertEqual((online.status, online.is_overpaying), ("confirmed", True))
        self.assertEqual((invoice.amount_owed, invoice.is_overpaid, invoice.payment_status), (-5_000_000, True, "paid"))
        self.assertFalse(invoice.payment_ids.filtered(lambda payment: payment.method != "online").is_overpaying)

    def test_paid_after_a_local_expiry_or_a_queued_cancel_still_records_the_money(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        expired, _ = self.create_link(invoice, amount=2_000_000)
        expired._advance_status("expired")
        self.notify(expired, 2_000_000, "FT1")
        self.assertEqual((expired.status, len(expired.payment_ids)), ("paid", 1))

        cancelled, fake = self.create_link(invoice, amount=3_000_000)
        fake.answers = {}
        self.pay(invoice, 3_000_000)
        self.assertEqual(self.job_items(JOB_CALLS, "pending").mapped("item_key"), [f"cancel:{cancelled.id}"])
        self.notify(cancelled, 3_000_000, "FT2", when="2026-03-04 10:00:00")

        self.assertEqual((cancelled.status, len(cancelled.payment_ids)), ("paid", 1))
        self.assertEqual((invoice.amount_owed, invoice.is_overpaid), (-3_000_000, True))

    def test_the_owed_check_runs_under_the_invoice_row_lock(self):
        invoice = self.create_invoice(lines=((5_000_000, 0),))
        first = self.pay(invoice, 3_000_000, user=self.salesperson)
        second = self.pay(invoice, 3_000_000, user=self.salesperson)
        statements = []
        original = type(self.env.cr).execute

        def spy(cr, query, *args, **kwargs):
            statements.append(str(getattr(query, "code", query)))
            return original(cr, query, *args, **kwargs)

        with patch.object(type(self.env.cr), "execute", spy):
            first.with_user(self.accountant.user_id).action_confirm()
            with self.assertRaisesRegex(UserError, "exceeds"):
                second.with_user(self.accountant.user_id).action_confirm()

        self.assertTrue(
            any("FOR NO KEY UPDATE" in statement and "medilab_invoice" in statement for statement in statements)
        )
        self.assertEqual((first.status, second.status, invoice.amount_owed), ("confirmed", "pending", 2_000_000))
