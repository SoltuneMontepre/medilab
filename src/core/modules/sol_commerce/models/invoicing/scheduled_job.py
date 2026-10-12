import logging
from datetime import timedelta

from odoo import fields, models

from odoo.addons.sol_commerce.services.payos_client import payos_client_from_env
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError

_logger = logging.getLogger(__name__)

POLL_AGAIN = timedelta(minutes=5)


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _handle_payos_calls(self, item):
        transaction = item._document()
        if not transaction or transaction.payos_checkout_url:
            return None
        client = payos_client_from_env()
        if client is None:
            # The item stays queued. Setting the secrets later lets the same item continue.
            _logger.error("PayOS credentials are not set")
            return fields.Datetime.now() + POLL_AGAIN
        order_code = int(transaction._payos_order_code())
        amount = int(transaction.amount)
        checkout_url = self._payos_checkout_url(client, order_code, amount)
        if not checkout_url:
            return fields.Datetime.now() + POLL_AGAIN
        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": checkout_url})
        transaction.with_context(payment_safe_write=True)._set_pending()
        self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", transaction.reference, document=transaction)
        return None

    def _payos_checkout_url(self, client, order_code, amount):
        remote = client.request("GET", f"/v2/payment-requests/{order_code}")
        data = (remote or {}).get("data") or {}
        if data:
            if not self._payos_link_matches(data, amount, order_code):
                raise PermanentJobError("PayOS link does not match this payment")
            return data.get("checkoutUrl")
        base = self.env["ir.config_parameter"].sudo().get_str("web.base.url")
        return_url = f"{base}/payment/payos/return"
        description = f"Medilab {order_code}"[:25]
        payload = {
            "orderCode": order_code,
            "amount": amount,
            "description": description,
            "cancelUrl": return_url,
            "returnUrl": return_url,
            "signature": client.payment_request_signature(amount, return_url, description, order_code, return_url),
        }
        body = client.request("POST", "/v2/payment-requests", payload) or {}
        return (body.get("data") or {}).get("checkoutUrl")

    def _payos_link_matches(self, data, amount, order_code):
        try:
            remote_amount = int(data.get("amount"))
            remote_code = int(data.get("orderCode"))
        except (TypeError, ValueError):
            return False
        return remote_amount == int(amount) and remote_code == int(order_code)

    def _handle_payos_poll(self, item):
        transaction = item._document()
        if not transaction:
            return None
        client = payos_client_from_env()
        if client is None:
            return fields.Datetime.now() + POLL_AGAIN
        order_code = transaction._payos_order_code()
        body = client.request("GET", f"/v2/payment-requests/{order_code}") or {}
        data = body.get("data") or body
        # amount on the payment request is what was asked. Money received is each transfer.
        self.env["payment.transaction"]._payos_record_transfers(order_code, data.get("transactions") or [])
        remaining = data.get("amountRemaining")
        if isinstance(remaining, (int, float)) and not isinstance(remaining, bool) and remaining > 0:
            return fields.Datetime.now() + POLL_AGAIN
        if data.get("status") == "PAID":
            return None
        if transaction._payos_expired() and not transaction.payos_bank_reference and transaction.state != "done":
            transaction.with_context(payment_safe_write=True)._process({"expired": True})
            return None
        return fields.Datetime.now() + POLL_AGAIN

    def _handle_overdue_reminders(self, item):
        # The customer's channel and Brevo come later. The job keeps the invoice and does not send.
        _logger.info("Overdue reminder waiting for a channel: %s", item.item_key)
