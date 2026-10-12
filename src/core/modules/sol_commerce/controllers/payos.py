import json

from odoo import http
from odoo.http import request

from odoo.addons.sol_commerce.services.payos_client import payos_client_from_env


class PayosController(http.Controller):
    @http.route("/payment/payos/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def payos_webhook(self):
        try:
            body = json.loads(request.httprequest.get_data(as_text=True) or "{}")
        except json.JSONDecodeError:
            return request.make_response("invalid", status=400)
        client = payos_client_from_env()
        data = body.get("data")
        if client is None or not client.matches(data, body.get("signature")):
            return request.make_response("invalid signature", status=400)
        request.env["payment.transaction"].sudo()._payos_apply_webhook(data)
        return request.make_response("ok", status=200)

    @http.route("/payment/payos/return", type="http", auth="public", csrf=False)
    def payos_return(self, **kwargs):
        # The browser coming back is not a payment. PayOS confirms it on the webhook.
        return request.make_response(
            "<html><body><p id='payos-return'>Waiting for PayOS to confirm the payment.</p></body></html>",
            headers=[("Content-Type", "text/html; charset=utf-8")],
        )
