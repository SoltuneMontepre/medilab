import hmac
import json
import os

from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.notifications import BREVO_WEBHOOK_TOKEN


class BrevoWebhook(http.Controller):
    """Brevo transactional webhooks. The token is the bearer token of the webhook auth object."""

    @http.route("/medilab/brevo/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def webhook(self):
        token = os.environ.get(BREVO_WEBHOOK_TOKEN) or ""
        header = request.httprequest.headers.get("Authorization") or ""
        presented = header[7:] if header.startswith("Bearer ") else ""
        if not token or not presented or not hmac.compare_digest(presented, token):
            return request.make_response("Unauthorized", status=401)
        try:
            payload = json.loads(request.httprequest.data or b"{}")
        except ValueError:
            return request.make_response("Bad Request", status=400)
        events = payload if isinstance(payload, list) else [payload]
        for event in events:
            if isinstance(event, dict):
                request.env["mail.notification"].sudo()._apply_brevo_event(event)
        return request.make_response("OK", status=200)
