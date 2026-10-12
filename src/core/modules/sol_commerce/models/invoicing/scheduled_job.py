from datetime import timedelta

from odoo import fields, models

from odoo.addons.sol_commerce.services.payos_client import payos_client_from_env
from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError

POLL_AGAIN = timedelta(minutes=5)


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _handle_payos_calls(self, item):
        transaction = item._document()
        if not transaction or transaction.payos_checkout_url:
            return
        client = payos_client_from_env()
        if client is None:
            raise PermanentJobError("PayOS credentials are not set")
        order_code = int(transaction._payos_order_code())
        base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        return_url = f"{base}/payment/payos/return"
        description = f"Medilab {order_code}"[:25]
        amount = int(transaction.amount)
        payload = {
            "orderCode": order_code,
            "amount": amount,
            "description": description,
            "cancelUrl": return_url,
            "returnUrl": return_url,
            "signature": client.payment_request_signature(amount, return_url, description, order_code, return_url),
        }
        body = client.request("POST", "/v2/payment-requests", payload)
        checkout_url = (body.get("data") or {}).get("checkoutUrl")
        transaction.with_context(payment_safe_write=True).write({"payos_checkout_url": checkout_url})
        transaction._set_pending()
        self.env[MODEL_SCHEDULED_JOB].queue("payos.poll", transaction.reference, document=transaction)

    def _handle_payos_poll(self, item):
        transaction = item._document()
        if not transaction or transaction.state in ("done", "error"):
            return None
        client = payos_client_from_env()
        if client is None:
            return None
        order_code = transaction._payos_order_code()
        body = client.request("GET", f"/v2/payment-requests/{order_code}")
        data = body.get("data") or body
        status = data.get("status")
        if status == "PAID":
            transaction.with_context(payment_safe_write=True)._process(
                {"paid": True, "amount": data.get("amount", transaction.amount), "bank_reference": data.get("reference")}
            )
            return None
        if transaction._payos_expired():
            transaction.with_context(payment_safe_write=True)._process({"expired": True})
            return None
        return fields.Datetime.now() + POLL_AGAIN
