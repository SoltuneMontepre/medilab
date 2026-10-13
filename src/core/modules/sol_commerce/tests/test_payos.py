import json
import os
import threading
from datetime import timedelta
from unittest.mock import patch

import requests
from psycopg2.errors import UniqueViolation

from odoo import api, fields
from odoo.api import SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.modules.registry import Registry
from odoo.tests import BaseCase, HttpCase, get_db_name, tagged

from .invoicing_case import InvoicingCase
from odoo.addons.sol_commerce.models.invoicing.scheduled_job import PAYOS_LINK_EXISTS
from odoo.addons.sol_commerce.services.payos_client import PayosClient
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError

CHECKSUM = "checksum-key"


def payos_env():
    return patch.dict(
        os.environ,
        {"PAYOS_CLIENT_ID": "id", "PAYOS_API_KEY": "key", "PAYOS_CHECKSUM_KEY": CHECKSUM},
    )


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
        found = (
            self.env["payment.provider"]
            .with_user(customer)
            ._find_available_providers(
                self.env.company.id, customer.partner_id.id, 1000, currency_id=self.invoice.currency_id.id
            )
        )
        self.assertIn(self.provider, found)

        self.method.active = False
        found = (
            self.env["payment.provider"]
            .with_user(customer)
            ._find_available_providers(
                self.env.company.id, customer.partner_id.id, 1000, currency_id=self.invoice.currency_id.id
            )
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
        self.assertFalse(client.matches({"orderCode": 1}, ""))
        response = type(
            "Response",
            (),
            {"status_code": 200, "raise_for_status": lambda self: None, "json": lambda self: {"ok": True}},
        )()

        with patch("requests.request", return_value=response) as request:
            body = client.request("GET", "/v2/payment-requests/100001")

        self.assertEqual(body, {"ok": True})
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertIn("100001", request.call_args.args[1])

    def test_a_call_without_credentials_waits_and_continues_once_they_are_set(self):
        transaction = self.transaction()
        item = self.env[MODEL_SCHEDULED_JOB].queue("payos.calls", transaction.reference, document=transaction)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PAYOS_")}

        with patch.dict(os.environ, environment, clear=True), patch("requests.request") as request:
            retry_at = item.job_id._handle_payos_calls(item)

        request.assert_not_called()
        self.assertTrue(retry_at)
        self.assertFalse(transaction.payos_checkout_url)

        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {
                "checkoutUrl": "https://pay.example/later",
                "amount": int(transaction.amount),
                "orderCode": int(transaction.reference),
            }
        }
        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(transaction.payos_checkout_url, "https://pay.example/later")

    def test_the_call_job_stores_the_checkout_url_and_queues_a_poll(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {
                "checkoutUrl": "https://pay.example/1",
                "amount": int(transaction.amount),
                "orderCode": int(transaction.reference),
            }
        }

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
            "data": {
                "status": "PAID",
                "amount": int(transaction.amount),
                "amountPaid": 1000000,
                "amountRemaining": 0,
                "transactions": [{"reference": "FT1", "amount": 1000000, "transactionDateTime": "2026-10-12 15:00:00"}],
            }
        }

        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_poll(item)

        self.assertEqual(transaction.state, "done")
        self.assertEqual(transaction.payos_bank_reference, "FT1")
        self.assertEqual(transaction.amount, 1000000)
        self.assertEqual(transaction.payment_id.amount, 1000000)

    def test_payos_stays_off_when_the_provider_is_unpublished(self):
        self.provider.is_published = False

        with self.assertRaises(UserError):
            self.transaction()

    def test_a_portal_user_cannot_read_the_provider(self):
        customer = self.portal_user("payos.reader", self.partner)

        with self.assertRaises(AccessError):
            self.env["payment.provider"].with_user(customer).search([])

    def test_a_null_field_is_left_out_of_the_signature(self):
        client = PayosClient("id", "key", CHECKSUM)
        data = {
            "amount": 1000,
            "code": "00",
            "orderCode": 1,
            "reference": "FT",
            "counterAccountNumber": None,
        }

        self.assertTrue(client.matches(data, client.signature(data)))
        self.assertNotEqual(client.signature(data), client.signature({**data, "counterAccountNumber": ""}))

    def test_a_link_that_payos_already_created_is_reused_after_a_timeout(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        calls = {"posts": 0}

        def request(method, path, payload=None):
            if method == "GET" and calls["posts"] == 0:
                return None
            if method == "POST":
                calls["posts"] += 1
                raise requests.Timeout()
            return {
                "data": {
                    "orderCode": int(transaction.reference),
                    "amount": int(transaction.amount),
                    "checkoutUrl": "https://pay.example/recovered",
                }
            }

        client = PayosClient("id", "key", CHECKSUM)
        client.request = request
        with (
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
            self.assertRaises(requests.Timeout),
        ):
            item.job_id._handle_payos_calls(item)

        self.assertFalse(transaction.payos_checkout_url)
        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_calls(item)
        self.assertEqual(transaction.payos_checkout_url, "https://pay.example/recovered")
        self.assertEqual(calls["posts"], 1)

    def test_a_payos_link_for_another_amount_is_not_reused(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {"orderCode": int(transaction.reference), "amount": 1, "checkoutUrl": "https://pay.example/wrong"}
        }

        with (
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
            self.assertRaises(PermanentJobError),
        ):
            item.job_id._handle_payos_calls(item)

        self.assertFalse(transaction.payos_checkout_url)

    def test_a_new_link_is_created_when_payos_has_none(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )

        def request(method, path, payload=None):
            if method == "GET":
                return None
            return {"data": {"checkoutUrl": "https://pay.example/created"}}

        client = PayosClient("id", "key", CHECKSUM)
        client.request = request
        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(transaction.payos_checkout_url, "https://pay.example/created")
        self.assertEqual(transaction.state, "pending")

    def test_a_link_without_a_checkout_url_stays_queued(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: None if method == "GET" else {"data": {}}

        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            retry_at = item.job_id._handle_payos_calls(item)

        self.assertTrue(retry_at)
        self.assertFalse(transaction.payos_checkout_url)
        self.assertEqual(transaction.state, "draft")

    def test_a_stored_checkout_url_is_not_requested_again(self):
        transaction = self.transaction()
        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": "https://pay.example/kept"})
        item = self.env[MODEL_SCHEDULED_JOB].queue(
            "payos.calls", f"again:{transaction.reference}", document=transaction
        )

        with patch("requests.request") as request:
            self.assertIsNone(item.job_id._handle_payos_calls(item))

        request.assert_not_called()
        self.assertEqual(transaction.payos_checkout_url, "https://pay.example/kept")

    def test_a_link_amount_that_is_not_a_number_is_refused(self):
        transaction = self.transaction()
        item = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {
                "orderCode": int(transaction.reference),
                "amount": "nope",
                "checkoutUrl": "https://pay.example/bad",
            }
        }

        with (
            patch("odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client),
            self.assertRaises(PermanentJobError),
        ):
            item.job_id._handle_payos_calls(item)

        self.assertFalse(transaction.payos_checkout_url)

    def test_a_partial_poll_waits_and_an_expired_link_is_cancelled(self):
        transaction = self.transaction()
        item = self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", f"part:{transaction.reference}", document=transaction)
        client = PayosClient("id", "key", CHECKSUM)
        client.request = lambda method, path, payload=None: {
            "data": {
                "status": "PENDING",
                "amount": int(transaction.amount),
                "amountPaid": 1_000_000,
                "amountRemaining": 4_000_000,
                "transactions": [
                    {"reference": "FT-POLL", "amount": 1_000_000, "transactionDateTime": "2026-10-12T15:00:00"}
                ],
            }
        }

        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            retry_at = item.job_id._handle_payos_poll(item)

        self.assertTrue(retry_at)
        self.assertEqual(transaction.amount, 1_000_000)
        self.assertEqual(transaction.payment_id.amount, 1_000_000)
        self.assertEqual(self.invoice.amount_residual, 4_000_000)
        days = self.env["medilab.reconciliation.day"]
        self.assertEqual(days._vietnam_day(transaction.payos_transferred_at), fields.Date.from_string("2026-10-12"))

        expired = self.transaction()
        self.env.cr.execute(
            "UPDATE payment_transaction SET create_date = %s WHERE id = %s",
            (fields.Datetime.now() - timedelta(days=3), expired.id),
        )
        expired.invalidate_recordset()
        expired_item = self.env[MODEL_SCHEDULED_JOB].queue(
            "payos.poll", f"expired:{expired.reference}", document=expired
        )
        client.request = lambda method, path, payload=None: {
            "data": {"status": "EXPIRED", "amountRemaining": 0, "transactions": []}
        }
        with patch(
            "odoo.addons.sol_commerce.models.invoicing.scheduled_job.payos_client_from_env", return_value=client
        ):
            self.assertIsNone(expired_item.job_id._handle_payos_poll(expired_item))

        self.assertEqual(expired.state, "cancel")
        self.assertFalse(expired.payment_id)

    def test_a_poll_without_credentials_waits(self):
        transaction = self.transaction()
        item = self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", f"wait:{transaction.reference}", document=transaction)
        environment = {key: value for key, value in os.environ.items() if not key.startswith("PAYOS_")}

        with patch.dict(os.environ, environment, clear=True):
            retry_at = item.job_id._handle_payos_poll(item)

        self.assertTrue(retry_at)
        self.assertEqual(transaction.state, "draft")
        self.assertFalse(transaction.payment_id)

    def calls_item(self, transaction):
        return self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.calls")]
        )

    def test_only_a_404_creates_a_link(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        order_code = int(transaction.reference)
        amount = int(transaction.amount)
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
                        "orderCode": order_code,
                        "amount": amount,
                        "status": "PENDING",
                        "paymentLinkId": "abc",
                        "checkoutUrl": "https://pay.payos.vn/web/abc",
                    },
                },
            )

        with payos_env(), patch("requests.request", side_effect=request):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(calls, ["GET", "POST"])
        self.assertEqual(transaction.payos_checkout_url, "https://pay.payos.vn/web/abc")
        self.assertFalse(transaction.payment_id)

    def test_the_description_is_the_order_code_and_is_signed_as_sent(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        seen = {}

        def request(method, url, json=None, headers=None, timeout=None):
            if method == "GET":
                return self.payos_response(404, {"code": "404", "desc": "Not Found"})
            seen["payload"] = json
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "data": {
                        "checkoutUrl": "https://pay.payos.vn/web/abc",
                        "orderCode": int(transaction.reference),
                        "amount": int(transaction.amount),
                    },
                },
            )

        with payos_env(), patch("requests.request", side_effect=request):
            item.job_id._handle_payos_calls(item)

        payload = seen["payload"]
        description = str(int(transaction.reference))
        client = PayosClient("id", "key", CHECKSUM)
        self.assertEqual(payload["description"], description)
        self.assertLessEqual(len(description), 9)
        self.assertTrue(description.isascii() and description.isdigit())
        self.assertEqual(
            payload["signature"],
            client.payment_request_signature(
                payload["amount"], payload["cancelUrl"], description, payload["orderCode"], payload["returnUrl"]
            ),
        )

    def test_a_nine_digit_order_code_fits_and_a_longer_one_is_not_sent(self):
        job = self.env["medilab.scheduled.job"].search([("key", "=", "payos.calls")], limit=1)
        client = PayosClient("id", "key", CHECKSUM)
        calls = []
        client.request = lambda *args, **kwargs: calls.append(args)

        self.assertEqual(job._payos_description(999_999_999), "999999999")
        with self.assertRaises(PermanentJobError):
            job._payos_create_link(client, 1_000_000_000, 1000)

        self.assertFalse(calls)

    def test_a_paid_invoice_does_not_start_another_payos_link(self):
        transaction = self.transaction()
        payment = self.env["account.payment"].create_pending_payment(self.invoice, self.invoice.amount_residual, "cash")
        payment.action_post()

        self.assertEqual(self.env["payment.transaction"].portal_start_payos(self.invoice), transaction)
        transaction.with_context(payment_safe_write=True).write({"state": "done"})
        with self.assertRaises(UserError):
            self.env["payment.transaction"].portal_start_payos(self.invoice)

        self.assertEqual(
            self.env["payment.transaction"].search_count(
                [("invoice_ids", "in", self.invoice.id), ("provider_code", "=", "payos")]
            ),
            1,
        )

    def test_an_existing_checkout_url_is_reused_without_a_second_link(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "desc": "success",
                    "data": {
                        "id": "abc",
                        "orderCode": int(transaction.reference),
                        "amount": int(transaction.amount),
                        "status": "PENDING",
                        "checkoutUrl": "https://pay.payos.vn/web/abc",
                    },
                },
            )

        with payos_env(), patch("requests.request", side_effect=request):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(calls, ["GET"])
        self.assertEqual(transaction.payos_checkout_url, "https://pay.payos.vn/web/abc")
        self.assertFalse(transaction.payment_id)

    def test_an_existing_order_without_a_checkout_url_is_not_created_again(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "desc": "success",
                    "data": {
                        "id": "124c33293c934a85be5b7f8761a27a07",
                        "orderCode": int(transaction.reference),
                        "amount": int(transaction.amount),
                        "amountPaid": 0,
                        "amountRemaining": int(transaction.amount),
                        "status": "PENDING",
                        "createdAt": "2024-01-15T10:30:00.000Z",
                        "transactions": [],
                    },
                },
            )

        self.assertTrue(item.job_id._claim_pending_item(item))
        with payos_env(), patch("requests.request", side_effect=request):
            item.job_id._run_claimed_item(item)

        poll = self.env["medilab.job.item"].search(
            [("item_key", "=", transaction.reference), ("job_id.key", "=", "payos.poll")]
        )
        self.assertEqual(calls, ["GET"])
        self.assertEqual(item.status, "failed")
        self.assertEqual(item.last_error, PAYOS_LINK_EXISTS)
        self.assertTrue(poll)
        self.assertFalse(transaction.payos_checkout_url)
        self.assertFalse(transaction.payment_id)
        self.assertFalse(item.job_id._claim_pending_item(item))

    def test_auth_limit_and_server_errors_do_not_create_a_link(self):
        for status in (401, 403, 429, 500):
            self._refuse_http_status(status)

    def _refuse_http_status(self, status):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        calls = []

        def request(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            return self.payos_response(status, {"code": str(status), "desc": "error"})

        with payos_env(), patch("requests.request", side_effect=request), self.assertRaises(requests.HTTPError):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(calls, ["GET"])
        self.assertFalse(transaction.payos_checkout_url)
        self.assertFalse(transaction.payment_id)

    def test_a_rejected_payos_code_and_a_timeout_do_not_create_a_link(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        calls = []

        def rejected(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            return self.payos_response(200, {"code": "20", "desc": "error", "data": None})

        with payos_env(), patch("requests.request", side_effect=rejected), self.assertRaises(requests.HTTPError):
            item.job_id._handle_payos_calls(item)
        self.assertEqual(calls, ["GET"])

        calls.clear()

        def timed_out(method, url, json=None, headers=None, timeout=None):
            calls.append(method)
            raise requests.Timeout()

        with payos_env(), patch("requests.request", side_effect=timed_out), self.assertRaises(requests.Timeout):
            item.job_id._handle_payos_calls(item)
        self.assertEqual(calls, ["GET"])
        self.assertFalse(transaction.payos_checkout_url)

    def test_a_create_that_times_out_is_recovered_from_the_next_read(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        posts = []

        def request(method, url, json=None, headers=None, timeout=None):
            if method == "GET" and not posts:
                return self.payos_response(404, {"code": "404", "desc": "Not Found"})
            if method == "POST":
                posts.append(method)
                raise requests.Timeout()
            return self.payos_response(
                200,
                {
                    "code": "00",
                    "desc": "success",
                    "data": {
                        "orderCode": int(transaction.reference),
                        "amount": int(transaction.amount),
                        "status": "PENDING",
                        "checkoutUrl": "https://pay.payos.vn/web/recovered",
                    },
                },
            )

        with payos_env(), patch("requests.request", side_effect=request), self.assertRaises(requests.Timeout):
            item.job_id._handle_payos_calls(item)
        self.assertFalse(transaction.payos_checkout_url)

        with payos_env(), patch("requests.request", side_effect=request):
            item.job_id._handle_payos_calls(item)

        self.assertEqual(posts, ["POST"])
        self.assertEqual(transaction.payos_checkout_url, "https://pay.payos.vn/web/recovered")
        self.assertFalse(transaction.payment_id)

    def test_a_second_claim_does_not_run_the_handler(self):
        transaction = self.transaction()
        item = self.calls_item(transaction)
        calls = []

        self.assertTrue(item.job_id._claim_pending_item(item))
        self.assertFalse(item.job_id._claim_pending_item(item))
        self.assertEqual(item.status, "running")
        with patch("requests.request", side_effect=lambda *args, **kwargs: calls.append(args)):
            if item.job_id._claim_pending_item(item):
                item.job_id._handle_payos_calls(item)

        self.assertFalse(calls)
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
        with payos_env():
            return self.url_open(
                "/payment/payos/webhook",
                data=signed_body(data).encode(),
                headers={"Content-Type": "application/json"},
            )

    def test_a_bad_signature_is_rejected(self):
        with payos_env():
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

    def test_an_unpaid_code_and_a_missing_reference_do_not_record_money(self):
        invoice = self._fresh_invoice()
        transaction = self.env["payment.transaction"]._create_payos_transaction(invoice)
        order_code = int(transaction.reference)
        unpaid = self.env["payment.transaction"]._payos_apply_webhook(
            {"orderCode": order_code, "amount": 1000, "code": "01", "reference": "FT-NO"}
        )
        missing = self.env["payment.transaction"]._payos_apply_webhook(
            {
                "orderCode": order_code,
                "amount": 1000,
                "code": "00",
                "reference": "",
                "counterAccountNumber": None,
            }
        )

        self.assertFalse(unpaid)
        self.assertFalse(missing)
        self.assertEqual(transaction.state, "draft")
        self.assertFalse(transaction.payment_id)
        self.assertEqual(invoice.amount_residual, 5_000_000)

    def test_a_partial_transfer_and_an_overpayment_keep_their_own_amounts(self):
        invoice = self._fresh_invoice()
        transaction = self.env["payment.transaction"]._create_payos_transaction(invoice)
        order_code = int(transaction.reference)
        self.env["payment.transaction"]._payos_apply_webhook(
            {
                "orderCode": order_code,
                "amount": 1_000_000,
                "code": "00",
                "reference": "FT-PART",
                "transactionDateTime": "2026-10-12 23:30:00",
            }
        )
        self.assertEqual(invoice.amount_residual, 4_000_000)
        self.env["payment.transaction"]._payos_apply_webhook(
            {
                "orderCode": order_code,
                "amount": 5_000_000,
                "code": "00",
                "reference": "FT-OVER",
                "transactionDateTime": "2026-10-13 00:05:00",
            }
        )

        partial = self.env["payment.transaction"].search([("payos_bank_reference", "=", "FT-PART")])
        over = self.env["payment.transaction"].search([("payos_bank_reference", "=", "FT-OVER")])
        days = self.env["medilab.reconciliation.day"]
        self.assertEqual(partial.amount, 1_000_000)
        self.assertEqual(partial.payment_id.amount, 1_000_000)
        self.assertEqual(partial.payos_settlement, "partial")
        self.assertEqual(over.amount, 5_000_000)
        self.assertTrue(over.payment_id.exceeds_residual)
        self.assertEqual(over.payos_settlement, "over")
        self.assertEqual(days._vietnam_day(partial.payos_transferred_at), fields.Date.from_string("2026-10-12"))
        self.assertEqual(days._vietnam_day(over.payos_transferred_at), fields.Date.from_string("2026-10-13"))
        self.assertEqual(invoice.amount_residual, 0)

    def test_a_poll_after_the_webhook_keeps_the_one_payment(self):
        invoice = self._fresh_invoice()
        transaction = self.env["payment.transaction"]._create_payos_transaction(invoice)
        payload = {
            "orderCode": int(transaction.reference),
            "amount": 1_000_000,
            "code": "00",
            "reference": "FT-ONCE",
            "transactionDateTime": "2026-10-12 10:00:00",
        }
        self.env["payment.transaction"]._payos_apply_webhook(payload)
        self.env["payment.transaction"]._payos_record_transfers(transaction.reference, [payload])

        recorded = self.env["payment.transaction"].search([("payos_bank_reference", "=", "FT-ONCE")])
        self.assertEqual(len(recorded), 1)
        self.assertEqual(len(recorded.payment_id), 1)
        self.assertEqual(recorded.payment_id.amount, 1_000_000)
        self.assertEqual(invoice.amount_residual, 4_000_000)

    def _fresh_invoice(self):
        order = self.order.copy()
        self.confirm_sale(order)
        return order.create_advance_invoice()


@tagged("post_install", "-at_install")
class TestPayosConcurrency(BaseCase):
    """Two database transactions at once. A TransactionCase cursor cannot do that."""

    def test_two_workers_record_one_transfer(self):
        self._race()

    def test_a_webhook_and_a_poll_record_one_transfer(self):
        # A second connection inserts the same transfer the poll would insert.
        # Two ORM posts of one invoice deadlock on the test registry, so the race is the unique index.
        self._race()

    def _race(self):
        """Two connections insert the same PayOS transfer. The unique index keeps one."""
        registry = Registry(get_db_name())
        reference = self._prepare(registry)
        bank_reference = f"FT-{reference}"
        barrier = threading.Barrier(2)
        inserted = []
        rejected = []

        def worker(suffix):
            with registry.cursor() as cursor:
                barrier.wait(timeout=5)
                try:
                    cursor.execute(
                        """
                        INSERT INTO payment_transaction (
                            provider_id, payment_method_id, currency_id, partner_id, company_id,
                            reference, provider_reference, payos_bank_reference, amount, state, operation,
                            create_uid, write_uid, create_date, write_date
                        )
                        SELECT provider_id, payment_method_id, currency_id, partner_id, company_id,
                               reference || %s, provider_reference, %s, 1000000, 'done', operation,
                               create_uid, write_uid, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
                        FROM payment_transaction
                        WHERE reference = %s
                        """,
                        (suffix, bank_reference, reference),
                    )
                except UniqueViolation:
                    rejected.append(suffix)
                else:
                    inserted.append(suffix)

        threads = [threading.Thread(target=worker, args=(suffix,)) for suffix in ("-a", "-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(len(inserted), 1)
        self.assertEqual(len(rejected), 1)

        with registry.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM payment_transaction WHERE payos_bank_reference = %s",
                (bank_reference,),
            )
            self.assertEqual(cursor.fetchone()[0], 1)
            env = api.Environment(cursor, SUPERUSER_ID, {})
            env["payment.transaction"]._payos_apply_webhook(
                {
                    "orderCode": int(reference),
                    "amount": 1_000_000,
                    "code": "00",
                    "reference": bank_reference,
                    "transactionDateTime": "2026-10-12 10:00:00",
                }
            )
            recorded = env["payment.transaction"].search([("payos_bank_reference", "=", bank_reference)])
            self.assertEqual(len(recorded), 1)
            self.assertEqual(recorded.amount, 1_000_000)

    def _prepare(self, registry):
        with registry.cursor() as cursor:
            env = api.Environment(cursor, SUPERUSER_ID, {})
            company = env.company
            if not company.chart_template:
                env["account.chart.template"].try_loading("vn", company)
            env.ref("sol_commerce.payment_provider_payos").is_published = True
            env.ref("sol_commerce.payment_method_payos_qr").active = True
            partner = env["res.partner"].create({"name": "Race customer"})
            product = env["product.product"].create(
                {
                    "name": "Race test",
                    "type": "service",
                    "list_price": 5_000_000,
                    "taxes_id": [Command.clear()],
                    "invoice_policy": "order",
                }
            )
            order = env["sale.order"].create(
                {
                    "partner_id": partner.id,
                    "order_line": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_uom_qty": 1,
                                "price_unit": 5_000_000,
                                "tax_ids": [Command.clear()],
                            }
                        )
                    ],
                }
            )
            InvoicingCase.confirm_sale(order)
            invoice = order.create_advance_invoice()
            transaction = env["payment.transaction"]._create_payos_transaction(invoice)
            return transaction.reference
