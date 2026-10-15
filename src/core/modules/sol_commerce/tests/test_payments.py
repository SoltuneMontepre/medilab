import re
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import requests

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_commerce.services.payos_client import PayosClient
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup

PAID_STATES = ("partial", "in_payment", "paid")


@tagged("post_install", "-at_install")
class TestPayments(InvoicingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.invoice = cls.order.create_advance_invoice()

    def pay(self, amount, method="bank_transfer"):
        return self.env["account.payment"].create_pending_payment(self.invoice, amount, method)

    def test_pending_amount_follows_drafts_and_drops_confirmed_and_rejected_payments(self):
        cash = self.pay(1_000_000, "cash")
        transfer = self.pay(500_000)
        order = self.invoice.order_id

        self.assertEqual(order.pending_amount, 1_500_000)
        self.assertEqual(order.payment_status, "not_paid")
        cash.action_post()
        self.assertEqual(order.pending_amount, 500_000)
        self.assertEqual(order.payment_status, "partial")
        transfer.rejection_reason = "Not received"
        transfer.action_reject_payment()
        self.assertEqual(order.pending_amount, 0)

    def test_a_new_payment_cannot_exceed_the_residual_and_a_received_transfer_is_kept(self):
        with self.assertRaises(UserError):
            self.pay(self.invoice.amount_residual + 1)
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        with self.assertRaises(UserError):
            self.env["payment.transaction"].portal_start_payos(self.invoice, self.invoice.amount_residual + 1)
        link = self.env["payment.transaction"].portal_start_payos(self.invoice, 1_000_000)
        self.assertEqual(link.amount, 1_000_000)
        with self.assertRaises(UserError):
            self.env["payment.transaction"].portal_start_payos(self.invoice, 2_000_000)
        self.assertEqual(self.env["payment.transaction"].portal_start_payos(self.invoice, 1_000_000), link)

    def test_an_empty_reconciliation_day_prints_zero_totals(self):
        day = self.env["medilab.reconciliation.day"].create({"day": "2020-06-01"})

        html = self.env["ir.actions.report"]._render_qweb_html("sol_commerce.report_reconciliation_day", day.ids)[0]

        self.assertEqual((day.transfer_total, day.payment_total, day.difference_total), (0, 0, 0))
        self.assertIn(b"medilab_reconciliation_day", html)
        self.assertIn(b"2020", html)
        self.assertIn(b"Open", html)

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
        moment = fields.Datetime.now()
        transaction.with_context(payment_safe_write=True).write({"payos_transferred_at": moment})
        transaction.with_context(payment_safe_write=True)._set_done()
        day = self.env["medilab.reconciliation.day"].create(
            {"day": self.env["medilab.reconciliation.day"]._vietnam_day(moment)}
        )

        self.assertIn(transaction, day.transaction_ids)
        self.assertEqual(day.missing_payment_count, 1)
        with self.assertRaises(UserError):
            day.action_lock()
        day.action_post_missing_payments()
        self.assertTrue(transaction.payment_id)
        self.assertEqual(day.missing_payment_count, 0)

        day.action_lock()
        html = self.env["ir.actions.report"]._render_qweb_html("sol_commerce.report_reconciliation_day", day.ids)[0]
        self.assertIn(b"medilab_transfer_total", html)
        self.assertEqual(day.transfer_total, transaction.amount)
        self.assertEqual(day.payment_total, transaction.payment_id.amount)
        self.assertEqual(day.difference_total, 0)
        self.assertIn(b"Locked", html)
        with self.assertRaises(UserError):
            transaction.payment_id.write({"amount": 1})
        with self.assertRaises(UserError):
            day.write({"status": "open"})

    def test_an_overpayment_blocks_the_lock_until_it_is_acknowledged(self):
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        transaction = self.env["payment.transaction"]._create_payos_transaction(self.invoice)
        paid = self.invoice.amount_total + 1
        self.env["payment.transaction"]._payos_apply_webhook(
            {
                "orderCode": int(transaction.reference),
                "amount": paid,
                "code": "00",
                "reference": "FT-LOCK-OVER",
                "transactionDateTime": "2026-10-12 11:00:00",
            }
        )
        day = self.env["medilab.reconciliation.day"].create({"day": "2026-10-12"})

        self.assertTrue(transaction.payment_id.exceeds_residual)
        self.assertEqual(transaction.payment_id.amount, paid)
        self.assertGreater(day.mismatch_count, 0)
        with self.assertRaises(UserError):
            day.action_lock()
        day.discrepancies_acknowledged = True
        day.action_lock()
        self.assertEqual(day.status, "locked")
        self.assertEqual(transaction.payment_id.amount, paid)

    def test_payos_after_the_lock_is_stored_as_recorded_after_the_lock(self):
        self.env.ref("sol_commerce.payment_provider_payos").is_published = True
        self.env.ref("sol_commerce.payment_method_payos_qr").active = True
        transaction = self.env["payment.transaction"]._create_payos_transaction(self.invoice)
        days = self.env["medilab.reconciliation.day"]
        moment = fields.Datetime.now()
        day = days.create({"day": days._vietnam_day(moment)})
        day.action_lock()
        local = days._vietnam_day(moment).strftime("%Y-%m-%d")

        confirmed = self.env["payment.transaction"]._payos_apply_webhook(
            {
                "orderCode": int(transaction.reference),
                "amount": 1_000_000,
                "code": "00",
                "reference": "FT-LATE",
                "transactionDateTime": f"{local} 15:00:00",
            }
        )

        self.assertEqual(confirmed, transaction)
        self.assertTrue(transaction.recorded_after_lock)
        self.assertEqual(transaction.state, "done")
        self.assertTrue(transaction.payment_id)

    def test_an_overdue_reminder_is_queued_once(self):
        state = self.invoice.payment_state
        today = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        self.invoice.invoice_date_due = today - timedelta(days=1)
        item = self.env[MODEL_SCHEDULED_JOB].queue("overdue.reminders", self.invoice.name, document=self.invoice)

        item.job_id._handle_overdue_reminders(item)
        item.job_id._handle_overdue_reminders(item)

        self.assertEqual(self.invoice.payment_state, state)
        self.assertEqual(
            self.env["mail.message"].search_count(
                [("notification_key", "=", f"invoice:{self.invoice.id}:overdue:{today.isoformat()}")]
            ),
            1,
        )


@tagged("post_install", "-at_install")
class TestPaymentPortal(AuditLookup, InvoicingCase, HttpCase):
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
        token = self.csrf_token()

        refused = self.url_open(f"/my/invoices/{self.invoice.id}/pay", data={"amount": "1"}, allow_redirects=False)
        self.assertEqual(refused.status_code, 400)
        self.assertFalse(
            self.env["account.payment"].search(
                [("invoice_ids", "in", self.invoice.id), ("method", "=", "bank_transfer")]
            )
        )

        response = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={"csrf_token": token, "method": "bank_transfer", "amount": "1000"},
            allow_redirects=False,
        )
        again = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={"csrf_token": token, "method": "bank_transfer", "amount": "9"},
            allow_redirects=False,
        )

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertIn(again.status_code, (301, 302, 303))
        payment = self.env["account.payment"].search(
            [("invoice_ids", "in", self.invoice.id), ("method", "=", "bank_transfer")]
        )
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 1_000)
        self.assertEqual(payment.state, "draft")
        self.assertEqual(self.invoice.order_id.pending_amount, 1_000)

    def test_a_portal_amount_above_the_residual_is_refused(self):
        self.authenticate(self.customer.login, self.customer.login)

        response = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={
                "csrf_token": self.csrf_token(),
                "method": "bank_transfer",
                "amount": str(self.invoice.amount_residual + 1),
            },
            allow_redirects=False,
        )

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))
        self.assertFalse(self.env["account.payment"].search([("invoice_ids", "in", self.invoice.id)]))

    def test_another_customer_cannot_pay_the_invoice(self):
        self.authenticate(self.other.login, self.other.login)

        response = self.url_open(
            f"/my/invoices/{self.private_invoice.id}/pay",
            data={"csrf_token": self.csrf_token(), "method": "bank_transfer", "amount": "1"},
            allow_redirects=False,
        )

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))
        self.assertFalse(self.env["account.payment"].search([("invoice_ids", "in", self.private_invoice.id)]))

    def test_another_customer_cannot_open_the_receipt(self):
        payment = self.env["account.payment"].create_pending_payment(self.invoice, 1_000_000, "bank_transfer")
        payment.action_post()
        self.authenticate(self.other.login, self.other.login)

        response = self.url_open(f"/my/invoices/{self.invoice.id}/receipt/{payment.id}", allow_redirects=False)

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))

    def test_the_owner_opens_the_receipt_and_not_someone_elses(self):
        payment = self.env["account.payment"].create_pending_payment(self.invoice, 1_000_000, "cash")
        payment.action_post()
        self.authenticate(self.customer.login, self.customer.login)

        receipt = self.url_open(f"/my/invoices/{self.invoice.id}/receipt/{payment.id}")
        missing = self.url_open(f"/my/invoices/{self.invoice.id}/receipt/999999", allow_redirects=False)

        self.assertEqual(receipt.status_code, 200)
        self.assertIn("1000000", receipt.text.replace(",", "").replace("\xa0", "").replace(" ", ""))
        self.assertIn(missing.status_code, (301, 302, 303))
        self.assertTrue(missing.headers["Location"].endswith("/my"))
        self.assertEqual(self.entries(payment, "download").user_id, self.customer)

    def test_payos_checkout_follows_the_provider_and_a_paid_invoice_is_refused(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = False
        method.active = False
        self.authenticate(self.customer.login, self.customer.login)
        token = self.csrf_token()

        refused = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={"csrf_token": token, "method": "payos"},
            allow_redirects=False,
        )
        self.assertEqual(refused.status_code, 200)
        self.assertIn("PayOS is turned off", refused.text)
        self.assertFalse(
            self.env["payment.transaction"].search(
                [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
            )
        )

        provider.is_published = True
        method.active = True
        started = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={"csrf_token": token, "method": "payos"},
            allow_redirects=False,
        )
        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(len(transaction), 1)
        self.assertEqual(started.status_code, 200)
        self.assertIn('id="payos-pending"', started.text)
        self.assertFalse(transaction.payment_id)

        payment = self.env["account.payment"].create_pending_payment(
            self.private_invoice, self.private_invoice.amount_residual, "cash"
        )
        payment.action_post()
        paid = self.url_open(
            f"/my/invoices/{self.private_invoice.id}/pay",
            data={"csrf_token": token, "method": "bank_transfer"},
            allow_redirects=False,
        )
        self.assertTrue(paid.headers["Location"].endswith("/my"))

    def _pay(self, invoice, method):
        return self.url_open(
            f"/my/invoices/{invoice.id}/pay",
            data={"csrf_token": self.csrf_token(), "method": method},
            allow_redirects=False,
        )

    def test_the_invoice_page_submits_payment_for_that_invoice(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)

        page = self.url_open(f"/my/invoices/{self.invoice.id}")
        actions = re.findall(r'action="([^"]*)"', page.text)

        self.assertEqual(page.status_code, 200)
        self.assertNotIn("#{invoice.id}", page.text)
        self.assertIn(f"/my/invoices/{self.invoice.id}/pay", actions)
        self.assertIn('value="payos"', page.text)
        self.assertIn('value="bank_transfer"', page.text)

        paid = self.url_open(
            f"/my/invoices/{self.invoice.id}/pay",
            data={
                "csrf_token": self.csrf_token(),
                "method": "bank_transfer",
                "amount": str(self.invoice.amount_residual),
            },
            allow_redirects=False,
        )
        payment = self.env["account.payment"].search(
            [("invoice_ids", "in", self.invoice.id), ("method", "=", "bank_transfer")]
        )
        self.assertIn(paid.status_code, (301, 302, 303))
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, self.invoice.amount_residual)

    def test_payos_waits_and_then_opens_the_same_link(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)

        waiting = self._pay(self.invoice, "payos")
        again = self._pay(self.invoice, "payos")
        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )

        self.assertEqual(waiting.status_code, 200)
        self.assertIn('id="payos-continue"', waiting.text)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": "https://pay.example/checkout"})
        checkout = self._pay(self.invoice, "payos")
        self.assertEqual(checkout.status_code, 303)
        self.assertEqual(checkout.headers["Location"], "https://pay.example/checkout")
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_a_ready_payos_link_redirects_once_and_a_bad_url_does_not(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        client = PayosClient("id", "key", "checksum-key")
        client.request = lambda method, path, payload=None: (
            None if method == "GET" else {"data": {"checkoutUrl": "https://pay.example/created"}}
        )

        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
        ):
            opened = self._pay(self.invoice, "payos")
            repeated = self._pay(self.invoice, "payos")

        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(opened.headers["Location"], "https://pay.example/created")
        self.assertEqual(repeated.headers["Location"], "https://pay.example/created")
        self.assertEqual(len(transaction), 1)
        self.assertFalse(
            self.env["account.payment"].search([("invoice_ids", "in", self.invoice.id), ("method", "=", "online")])
        )

        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": "javascript:alert(1)"})
        refused = self._pay(self.invoice, "payos")
        self.assertEqual(refused.status_code, 200)
        self.assertIn('id="payos-unavailable"', refused.text)
        self.assertFalse(refused.headers.get("Location"))

    def test_a_payos_timeout_leaves_the_one_unpaid_transaction(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        client = PayosClient("id", "key", "checksum-key")

        def request(method, path, payload=None):
            raise requests.Timeout()

        client.request = request
        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
        ):
            waiting = self._pay(self.invoice, "payos")

        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(waiting.status_code, 200)
        self.assertIn('id="payos-pending"', waiting.text)
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_a_payos_link_for_the_wrong_amount_is_not_opened(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        client = PayosClient("id", "key", "checksum-key")
        client.request = lambda method, path, payload=None: {
            "data": {"amount": 1, "orderCode": 1, "checkoutUrl": "https://pay.example/wrong"}
        }

        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
        ):
            refused = self._pay(self.invoice, "payos")

        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(refused.status_code, 200)
        self.assertIn('id="payos-unavailable"', refused.text)
        self.assertFalse(refused.headers.get("Location"))
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_a_finished_payos_job_without_a_link_stays_pending(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)

        waiting = self._pay(self.invoice, "payos")
        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        item = self.env["medilab.job.item"].search([("item_key", "=", transaction.reference)])
        item.status = "done"
        again = self._pay(self.invoice, "payos")

        self.assertEqual(waiting.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertIn('id="payos-pending"', again.text)
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_another_customer_cannot_start_payos(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.other.login, self.other.login)

        response = self._pay(self.invoice, "payos")

        self.assertIn(response.status_code, (301, 302, 303))
        self.assertTrue(response.headers["Location"].endswith("/my"))
        self.assertFalse(
            self.env["payment.transaction"].search(
                [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
            )
        )

    def test_the_portal_creates_a_link_when_payos_reports_the_order_missing(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            if method == "GET":
                return self.payos_response(404, {"code": "404", "desc": "Not Found"})
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "desc": "success",
                    "data": {
                        "status": "PENDING",
                        "paymentLinkId": "abc",
                        "checkoutUrl": "https://pay.payos.vn/web/abc",
                    },
                },
            )

        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("requests.request", side_effect=request),
        ):
            opened = self._pay(self.invoice, "payos")

        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(calls, ["GET", "POST"])
        self.assertEqual(opened.status_code, 303)
        self.assertEqual(opened.headers["Location"], "https://pay.payos.vn/web/abc")
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_the_portal_stops_when_payos_has_no_checkout_url(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            order_code = int(url.rstrip("/").rsplit("/", 1)[-1])
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "desc": "success",
                    "data": {
                        "id": "124c33293c934a85be5b7f8761a27a07",
                        "orderCode": order_code,
                        "amount": int(self.invoice.amount_residual),
                        "amountPaid": 0,
                        "amountRemaining": int(self.invoice.amount_residual),
                        "status": "PENDING",
                        "transactions": [],
                    },
                },
            )

        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("requests.request", side_effect=request),
        ):
            refused = self._pay(self.invoice, "payos")
            again = self._pay(self.invoice, "payos")

        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        self.assertEqual(calls, ["GET"])
        self.assertEqual(refused.status_code, 200)
        self.assertIn('id="payos-unavailable"', refused.text)
        self.assertIn("did not return a checkout URL", refused.text)
        self.assertEqual(again.status_code, 200)
        self.assertIn('id="payos-unavailable"', again.text)
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def test_a_running_payos_job_is_not_called_again(self):
        provider = self.env.ref("sol_commerce.payment_provider_payos")
        method = self.env.ref("sol_commerce.payment_method_payos_qr")
        provider.is_published = True
        method.active = True
        self.authenticate(self.customer.login, self.customer.login)
        waiting = self._pay(self.invoice, "payos")
        transaction = self.env["payment.transaction"].search(
            [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
        )
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        item.status = "running"
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            return self.payos_response(500, {"code": "500", "desc": "error"})

        with (
            patch.dict(
                "os.environ",
                {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": "checksum-key"},
            ),
            patch("requests.request", side_effect=request),
        ):
            again = self._pay(self.invoice, "payos")

        self.assertEqual(waiting.status_code, 200)
        self.assertIn('id="payos-pending"', waiting.text)
        self.assertEqual(again.status_code, 200)
        self.assertIn('id="payos-pending"', again.text)
        self.assertFalse(calls)
        self.assertEqual(len(transaction), 1)
        self.assertFalse(transaction.payment_id)

    def payos_response(self, status, body):
        def raise_for_status():
            if status >= 400:
                raise requests.HTTPError(f"HTTP {status}")

        return type(
            "Response",
            (),
            {"status_code": status, "json": lambda self: body, "raise_for_status": lambda self: raise_for_status()},
        )()
