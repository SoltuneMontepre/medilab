from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB

PAID_STATES = ("partial", "in_payment", "paid")


@tagged("post_install", "-at_install")
class TestPayments(InvoicingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.order.create_advance_invoice()

    def pay(self, amount, method="bank_transfer"):
        return self.env["account.payment"].create_pending_payment(self.invoice, amount, method)

    def test_a_draft_payment_leaves_the_invoice_unpaid(self):
        payment = self.pay(1_000_000)

        self.assertEqual(payment.state, "draft")
        self.assertEqual(self.invoice.payment_state, "not_paid")
        self.assertEqual(self.invoice.amount_residual, 5_000_000)

    def test_the_accountant_confirms_a_partial_payment(self):
        payment = self.pay(1_000_000)
        payment.action_post()

        self.assertEqual(self.invoice.amount_residual, 4_000_000)
        self.assertIn(self.invoice.payment_state, PAID_STATES)
        self.assertTrue(payment.name and payment.name != "/")
        self.assertEqual(payment.reviewed_by_id, self.env.user)

    def test_cash_and_a_second_transfer_cannot_pass_what_is_owed(self):
        with self.assertRaises(UserError):
            self.pay(self.invoice.amount_residual + 1, "cash")

        first = self.pay(self.invoice.amount_residual)
        second = self.pay(self.invoice.amount_residual)
        first.action_post()
        with self.assertRaises(UserError):
            second.action_post()

    def test_rejecting_a_draft_tells_the_salesperson_and_leaves_the_invoice(self):
        payment = self.pay(1_000_000)
        payment.rejection_reason = "The transfer never arrived"
        payment.action_reject_payment()

        self.assertEqual(payment.state, "canceled")
        self.assertEqual(self.invoice.payment_state, "not_paid")
        activity = self.env["mail.activity"].search([("res_model", "=", payment._name), ("res_id", "=", payment.id)])
        self.assertEqual(activity.user_id, self.invoice.invoice_user_id)
        self.assertIn("never arrived", activity.note)

    def test_a_clerk_cannot_confirm_a_payment(self):
        payment = self.pay(1_000_000)
        clerk = self.env["res.users"].create(
            {"name": "Clerk", "login": "payment.clerk", "group_ids": [Command.set(self.env.ref("base.group_user").ids)]}
        )

        with self.assertRaises(AccessError):
            payment.with_user(clerk).action_post()

    def test_a_payos_amount_above_the_residual_is_flagged_on_the_payment(self):
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        transaction = self.env["payment.transaction"]._create_payos_transaction(self.invoice)
        transaction.with_context(payment_safe_write=True).write({"amount": self.invoice.amount_residual + 1_000})
        transaction.with_context(payment_safe_write=True)._set_done()

        payment = transaction._create_online_payment()

        self.assertTrue(payment.exceeds_residual)
        self.assertEqual(payment.method, "online")
        self.assertEqual(payment.amount, self.invoice.amount_total + 1_000)
        self.assertIn(self.invoice.payment_state, PAID_STATES)

    def test_the_receipt_names_the_collection_method(self):
        payment = self.pay(1_000_000, "cash")
        payment.action_post()

        html = self.env["ir.actions.report"]._render_qweb_html("account.action_report_payment_receipt", payment.ids)[0]

        self.assertIn(b"medilab_payment_method", html)
        self.assertIn(payment.name.encode(), html)

    def test_the_invoice_pdf_uses_the_localisation_qr(self):
        invoice_report = self.env.ref("account.report_invoice_document").arch_db
        laboratory = self.env.ref("sol_commerce.report_invoice_document_laboratory").arch_db

        self.assertIn("_generate_qr_code", invoice_report)
        self.assertNotIn("qr", laboratory.lower())

    def test_a_missing_payos_payment_is_posted_from_the_day_and_the_day_then_locks(self):
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        transaction = self.env["payment.transaction"]._create_payos_transaction(self.invoice)
        transaction.with_context(payment_safe_write=True)._set_done()
        day = self.env["medilab.reconciliation.day"].create(
            {"day": self.env["medilab.reconciliation.day"]._vietnam_day(transaction.create_date)}
        )

        self.assertIn(transaction, day.transaction_ids)
        self.assertEqual(day.missing_payment_count, 1)
        day.action_post_missing_payments()
        self.assertTrue(transaction.payment_id)
        self.assertEqual(day.missing_payment_count, 0)

        day.action_lock()
        with self.assertRaises(UserError):
            transaction.payment_id.write({"amount": 1})
        with self.assertRaises(UserError):
            day.write({"status": "open"})

    def test_payos_after_the_lock_is_stored_as_recorded_after_the_lock(self):
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        transaction = self.env["payment.transaction"]._create_payos_transaction(self.invoice)
        day = self.env["medilab.reconciliation.day"].create(
            {"day": self.env["medilab.reconciliation.day"]._vietnam_day(transaction.create_date)}
        )
        day.action_lock()

        confirmed = self.env["payment.transaction"]._payos_apply_webhook(
            {"orderCode": int(transaction.reference), "amount": 1_000_000, "code": "00", "reference": "FT-LATE"}
        )

        self.assertEqual(confirmed, transaction)
        self.assertTrue(transaction.recorded_after_lock)
        self.assertEqual(transaction.state, "done")
        self.assertTrue(transaction.payment_id)

    def test_the_overdue_reminder_job_does_not_send(self):
        before = self.env["mail.mail"].search_count([])
        item = self.env[MODEL_SCHEDULED_JOB].queue("overdue.reminders", self.invoice.name, document=self.invoice)

        item.job_id._handle_overdue_reminders(item)

        self.assertEqual(self.env["mail.mail"].search_count([]), before)


@tagged("post_install", "-at_install")
class TestPaymentPortal(InvoicingCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.order.create_advance_invoice()
        private_order = cls.order.copy()
        cls.confirm_sale(private_order)
        cls.private_invoice = private_order.create_advance_invoice()
        cls.customer = cls.portal_user("payer.customer", cls.partner)
        cls.other = cls.portal_user("payer.other", cls.env["res.partner"].create({"name": "Other customer"}))

    def test_a_customer_pays_their_invoice_for_the_amount_still_owed(self):
        self.authenticate(self.customer.login, self.customer.login)

        response = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay", data={"amount": "1"}, allow_redirects=False
        )

        self.assertIn(response.status_code, (301, 302, 303))
        payment = self.env["account.payment"].search([("invoice_ids", "in", self.invoice.id), ("method", "=", "bank_transfer")])
        self.assertEqual(payment.amount, self.invoice.amount_residual)

    def test_another_customer_cannot_pay_the_invoice(self):
        self.authenticate(self.other.login, self.other.login)

        response = self.url_open(
            f"/my/invoices/{self.private_invoice.id}/pay", data={"amount": "1"}, allow_redirects=False
        )

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))
        self.assertFalse(self.env["account.payment"].search([("invoice_ids", "in", self.private_invoice.id)]))
