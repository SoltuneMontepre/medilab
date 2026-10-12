import json
import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_commerce.services.payos_client import PayosClient
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError

CHECKSUM = "checksum-key"


def signed_body(data):
    return json.dumps({"code": "00", "data": data, "signature": PayosClient("id", "key", CHECKSUM).signature(data)})


@tagged("post_install", "-at_install")
class TestPayos(InvoicingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("sol_commerce.payment_provider_payos")
        cls.method = cls.env.ref("sol_commerce.payment_method_payos_qr")
        cls.provider.is_published = True
        cls.method.active = True
        cls.invoice = cls.order.create_advance_invoice()

    def transaction(self):
        return self.env["payment.transaction"]._create_payos_transaction(self.invoice)

    def test_the_portal_shows_payos_only_when_the_method_is_on(self):
        customer = self.portal_user("payos.customer", self.partner)
        found = self.env["payment.provider"].with_user(customer)._find_available_providers(
            self.env.company.id, customer.partner_id.id, 1000, currency_id=self.invoice.currency_id.id
        )
        self.assertIn(self.provider, found)

        self.method.active = False
        found = self.env["payment.provider"].with_user(customer)._find_available_providers(
            self.env.company.id, customer.partner_id.id, 1000, currency_id=self.invoice.currency_id.id
        )
        self.assertNotIn(self.provider, found)

    def test_turning_payos_on_publishes_the_provider_and_the_method(self):
        self.provider.is_published = False
        self.method.active = False
        settings = self.env["res.config.settings"].create(
            {"payos_enabled": True, "payos_qr_enabled": True, "payos_expiry_hours": 12}
        )
        settings.set_values()

        self.assertTrue(self.provider.is_published)
        self.assertTrue(self.method.active)
        self.assertEqual(self.env["res.config.settings"]._get_parameter("payos_expiry_hours"), 12)

    def test_payos_declares_qr_and_no_refunds(self):
        self.provider.invalidate_recordset(["support_refund", "support_tokenization"])

        self.assertEqual(self.provider.support_refund, "none")
        self.assertFalse(self.provider.support_tokenization)
        self.assertEqual(self.provider._get_default_payment_method_codes(), {"qr"})
        other = self.env["payment.provider"].create({"name": "Manual", "code": "none"})
        self.assertNotEqual(other._get_default_payment_method_codes(), {"qr"})
        other.with_context(force_delete=True).unlink()
        self.assertFalse(other.exists())

    def test_the_client_rejects_a_bad_payload_and_logs_the_call(self):
        client = PayosClient("id", "key", CHECKSUM)
        self.assertFalse(client.matches("nope", "sig"))
        response = type("Response", (), {"raise_for_status": lambda self: None, "json": lambda self: {"ok": True}})()

        with patch("requests.request", return_value=response) as request:
            body = client.request("GET", "/v2/payment-requests/100001")

        self.assertEqual(body, {"ok": True})
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertIn("100001", request.call_args.args[1])

    def test_a_call_without_credentials_does_not_reach_payos(self):
        transaction = self.transaction()
        item = self.env[MODEL_SCHEDULED_JOB].queue("payos.calls", transaction.reference, document=transaction)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PAYOS_")}

        with patch.dict(os.environ, environment, clear=True), patch("requests.request") as request, self.assertRaises(
            PermanentJobError
        ):
            item.job_id._handle_payos_calls(item)

        request.assert_not_called()
        self.assertFalse(transaction.payos_checkout_url)

    def test_the_call_job_stores_the_checkout_url_and_queues_a_poll(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {"data": {"checkoutUrl": "https://pay.example/1"}}

        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(transaction.payos_checkout_url, "https://pay.example/1")
        self.assertEqual(transaction.state, "pending")
        poll = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.poll")]
        )
        self.assertTrue(poll)

    def test_a_paid_poll_after_expiry_still_confirms(self):
        transaction = self.transaction()
        transaction.with_context(payment_safe_write=True).write(
            {"state": "cancel", "create_date": fields.Datetime.now() - timedelta(days=3)}
        )
        item = self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", f"late:{transaction.reference}", document=transaction)
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {"status": "PAID", "amount": 1000000, "reference": "FT1"}
        }

        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_poll(item)

        self.assertEqual(transaction.state, "done")
        self.assertEqual(transaction.payos_bank_reference, "FT1")

    def test_payos_stays_off_when_the_provider_is_unpublished(self):
        self.provider.is_published = False

        with self.assertRaises(UserError):
            self.transaction()


@tagged("post_install", "-at_install")
class TestPayosWebhook(InvoicingCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("sol_commerce.payment_provider_payos")
        cls.method = cls.env.ref("sol_commerce.payment_method_payos_qr")
        cls.provider.is_published = True
        cls.method.active = True
        cls.invoice = cls.order.create_advance_invoice()
        cls.transaction = cls.env["payment.transaction"]._create_payos_transaction(cls.invoice)

    def post_webhook(self, data):
        os.environ["PAYOS_CLIENT_ID"] = "id"
        os.environ["PAYOS_API_KEY"] = "key"
        os.environ["PAYOS_CHECKSUM_KEY"] = CHECKSUM
        return self.url_open(
            "/payment/payos/webhook",
            data=signed_body(data).encode(),
            headers={"Content-Type": "application/json"},
        )

    def test_a_bad_signature_is_rejected(self):
        os.environ["PAYOS_CLIENT_ID"] = "id"
        os.environ["PAYOS_API_KEY"] = "key"
        os.environ["PAYOS_CHECKSUM_KEY"] = CHECKSUM
        response = self.url_open(
            "/payment/payos/webhook",
            data=b'{"data": {"orderCode": 1}, "signature": "nope"}',
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.transaction.state, "draft")

    def test_a_repeated_webhook_does_not_create_a_second_transaction(self):
        data = {"orderCode": int(self.transaction.reference), "amount": 1000000, "code": "00", "reference": "FT1"}

        first = self.post_webhook(data)
        second = self.post_webhook(data)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        transactions = self.env["payment.transaction"].search([("provider_reference", "=", self.transaction.reference)])
        self.assertEqual(transactions, self.transaction)
        self.assertEqual(self.transaction.state, "done")

    def test_a_second_bank_reference_is_another_transaction_for_the_same_invoice(self):
        order_code = int(self.transaction.reference)
        self.post_webhook({"orderCode": order_code, "amount": 1000000, "code": "00", "reference": "FT1"})
        self.post_webhook({"orderCode": order_code, "amount": 500000, "code": "00", "reference": "FT2"})

        transactions = self.env["payment.transaction"].search([("provider_reference", "=", self.transaction.reference)])
        self.assertEqual(len(transactions), 2)
        self.assertEqual(set(transactions.mapped("invoice_ids").ids), {self.invoice.id})
        self.assertEqual(transactions.filtered(lambda tx: tx.payos_bank_reference == "FT2").amount, 500000)

    def test_the_return_url_does_not_confirm_the_payment(self):
        self.transaction.with_context(payment_safe_write=True)._set_pending()

        response = self.url_open(f"/payment/payos/return?orderCode={self.transaction.reference}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Waiting for PayOS", response.text)
        self.assertEqual(self.transaction.state, "pending")
