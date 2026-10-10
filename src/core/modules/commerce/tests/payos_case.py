import os
from datetime import timedelta
from unittest.mock import patch

from odoo import fields

from .invoicing_case import InvoicingCase
from odoo.addons.commerce.constants.models import MODEL_PAYMENT_LINK
from odoo.addons.commerce.constants.payos import JOB_CALLS, JOB_POLL, SUCCESS_CODE
from odoo.addons.commerce.services.payos_client import PayosClient, sign
from odoo.addons.laboratory.constants.models import MODEL_JOB_ITEM, MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB

CREDENTIALS = {
    "PAYOS_CLIENT_ID": "test-client-id",
    "PAYOS_API_KEY": "test-api-key",
    "PAYOS_CHECKSUM_KEY": "test-checksum-key",
}
PAYMENT_LINK_PERMISSIONS = (
    "payment.link.read.all",
    "payment.link.create.all",
    "payment.link.edit.all",
    "payment.link.transaction.read.all",
)
LINK_LOGGER = "odoo.addons.commerce.models.invoicing.payment_link"
JOB_LOGGER = "odoo.addons.laboratory.models.system.scheduled_job"
CREATE_PATH = ("POST", "/v2/payment-requests")
GET_PATH = ("GET", "/v2/payment-requests/")


def signed_answer(data, code=SUCCESS_CODE, desc="success"):
    """A PayOS answer as the API returns it, signed like PayOS signs its data."""
    return {"code": code, "desc": desc, "data": data, "signature": sign(data, CREDENTIALS["PAYOS_CHECKSUM_KEY"])}


def refusal(desc="Đơn thanh toán đã tồn tại", code="231"):
    return {"code": code, "desc": desc, "data": None, "signature": None}


def created_data(order_code, amount, payment_link_id="payoslink0001"):
    return {
        "bin": "970436",
        "accountNumber": "0011001234567",
        "accountName": "CONG TY TNHH MEDILAB",
        "amount": int(amount),
        "description": "000126HD",
        "orderCode": order_code,
        "currency": "VND",
        "paymentLinkId": payment_link_id,
        "status": "PENDING",
        "checkoutUrl": f"https://pay.payos.vn/web/{payment_link_id}",
        "qrCode": "00020101021238570010A000000727",
    }


def link_data(link, status="PENDING", transactions=(), amount=None):
    transactions = list(transactions)
    paid = sum(transaction["amount"] for transaction in transactions)
    amount = int(link.amount if amount is None else amount)
    return {
        "id": link.provider_payment_link_id or "payoslink0001",
        "orderCode": link.provider_order_code,
        "amount": amount,
        "amountPaid": paid,
        "amountRemaining": amount - paid,
        "status": status,
        "createdAt": "2026-03-02T09:15:00+07:00",
        "transactions": transactions,
        "cancellationReason": None,
        "canceledAt": None,
    }


def transaction(reference, amount, when="2026-03-03 10:15:00"):
    return {
        "reference": reference,
        "amount": amount,
        "accountNumber": "0011001234567",
        "description": "000126HD",
        "transactionDateTime": when,
        "virtualAccountName": None,
        "virtualAccountNumber": None,
        "counterAccountBankId": "970422",
        "counterAccountBankName": "MB Bank",
        "counterAccountName": "CONG TY TNHH THUC PHAM SAO MAI",
        "counterAccountNumber": "0987654321",
    }


def webhook_payload(link, amount, reference, when="2026-03-03 10:15:00", code=SUCCESS_CODE, key=None):
    """A PayOS notification for one transfer, signed with the checksum key unless another key is given."""
    data = {
        "orderCode": link.provider_order_code,
        "amount": amount,
        "description": "000126HD",
        "accountNumber": "0011001234567",
        "reference": reference,
        "transactionDateTime": when,
        "currency": "VND",
        "paymentLinkId": link.provider_payment_link_id or "payoslink0001",
        "code": code,
        "desc": "success" if code == SUCCESS_CODE else "failed",
        "counterAccountBankId": "970422",
        "counterAccountBankName": "MB Bank",
        "counterAccountName": "CONG TY TNHH THUC PHAM SAO MAI",
        "counterAccountNumber": "0987654321",
        "virtualAccountName": None,
        "virtualAccountNumber": None,
    }
    return {
        "code": SUCCESS_CODE,
        "desc": "success",
        "success": True,
        "data": data,
        "signature": sign(data, key or CREDENTIALS["PAYOS_CHECKSUM_KEY"]),
    }


def answer_creation(method, path, body):
    return signed_answer(created_data(body["orderCode"], body["amount"]))


class FakePayos:
    """Answers PayOS calls from a script of answers, or callables, per method and path prefix."""

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.calls = []

    def __call__(self, method, path, body):
        self.calls.append((method, path, body))
        # The longest matching prefix answers, so the cancel path is not taken for the creation path.
        matching = [
            (len(prefix), answer)
            for (answer_method, prefix), answer in self.answers.items()
            if method == answer_method and path.startswith(prefix)
        ]
        if not matching:
            raise AssertionError(f"Unexpected PayOS call {method} {path}")
        answer = max(matching, key=lambda match: match[0])[1]
        return answer(method, path, body) if callable(answer) else answer

    def paths(self):
        return [(method, path) for method, path, _ in self.calls]


def enable_payos(test_class):
    """Credentials in the environment for the whole class, and PayOS turned on in the settings."""
    environ = patch.dict(os.environ, CREDENTIALS)
    environ.start()
    test_class.addClassCleanup(environ.stop)
    test_class.env[MODEL_RES_CONFIG_SETTINGS].create({"payos_enabled": True}).set_values()


def fake_payos(test, answers=None):
    """Replace the network call of the client for one test; returns the fake, which records every call."""
    fake = FakePayos(answers)
    patcher = patch.object(PayosClient, "_request", fake)
    patcher.start()
    test.addCleanup(patcher.stop)
    return fake


class PayosCase(InvoicingCase):
    """PayOS enabled with test credentials, the accountant holding the payment link permissions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        enable_payos(cls)
        cls.grant(cls.accountant, *PAYMENT_LINK_PERMISSIONS)
        # The demo data may hold queued PayOS items; the tests start from an empty queue.
        cls.env[MODEL_JOB_ITEM].search([("job_id.key", "in", (JOB_CALLS, JOB_POLL))]).unlink()

    def fake_payos(self, answers=None):
        return fake_payos(self, answers)

    def create_link(self, invoice=None, amount=None, user=None, answers=None):
        """A link created by the accountant against a PayOS that answers the creation at once."""
        invoice = invoice or self.create_invoice()
        fake = self.fake_payos(answers if answers is not None else {CREATE_PATH: answer_creation})
        links = self.env[MODEL_PAYMENT_LINK].with_user((user or self.accountant).user_id)
        link = links._create_for_invoice(invoice, invoice.amount_owed if amount is None else amount)
        return link.with_env(self.env), fake

    def run_job(self, key):
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(key)
        with self.registry_test_mode():
            job.cron_id.method_direct_trigger()
        self.env.invalidate_all()
        return job.run_ids.sorted("id")[-1:]

    def job_items(self, key, status=None):
        domain = [("job_id.key", "=", key)]
        if status:
            domain.append(("status", "=", status))
        return self.env[MODEL_JOB_ITEM].search(domain, order="id")

    @staticmethod
    def hours_from_now(hours):
        return fields.Datetime.now() + timedelta(hours=hours)
