from odoo.http import Controller, request, route

from odoo.addons.commerce.constants.models import MODEL_PAYMENT_LINK
from odoo.addons.commerce.constants.payos import WEBHOOK_ROUTE
from odoo.addons.commerce.services.payos_client import PayosClient


# PayOS posts a signed notification here for each transfer; only a notification whose signature is right changes anything.
class PayosWebhook(Controller):
    @route(WEBHOOK_ROUTE, type="http", auth="public", methods=["POST"], csrf=False)
    def notify(self):
        try:
            payload = request.get_json_data()
        except ValueError:
            return request.make_json_response({"success": False}, status=400)
        data = PayosClient().verify_webhook(payload)
        if data is None:
            return request.make_json_response({"success": False}, status=400)
        request.env[MODEL_PAYMENT_LINK].sudo()._handle_webhook(data)
        return request.make_json_response({"success": True})
