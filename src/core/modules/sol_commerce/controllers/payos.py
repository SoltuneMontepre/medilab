import json

from odoo import http
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_TRANSACTION
from odoo.addons.sol_commerce.services.payos_client import payos_client_from_env
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY
from odoo.addons.sol_laboratory.services.request_env import request_env


class PayosController(http.Controller):
    @http.route("/payment/payos/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def payos_webhook(self):
        entries = request_env()[MODEL_AUDIT_ENTRY]
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            entries._log_event("error", request_env()._("PayOS webhook refused: the body is not JSON"))
            return request.make_response("invalid", status=400)
        client = payos_client_from_env()
        data = body.get("data")
        if client is None or not client.matches(data, body.get("signature")):
            entries._log_event("error", request_env()._("PayOS webhook refused: the signature does not match"))
            return request.make_response("invalid signature", status=400)
        transactions = request_env()[MODEL_PAYMENT_TRANSACTION].sudo()._payos_apply_webhook(data)
        entries._log_event(
            "integration",
            request_env()._("PayOS reported a transfer for the payment link %s", data.get("orderCode")),
            transactions or None,
        )
        return request.make_response("ok", status=200)

    @http.route("/payment/payos/return", type="http", auth="public", csrf=False)
    def payos_return(self, **kwargs):
        # The browser coming back is not a payment. PayOS confirms it on the webhook.
        return request.make_response(
            "<html><body><p id='payos-return'>Waiting for PayOS to confirm the payment.</p></body></html>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
