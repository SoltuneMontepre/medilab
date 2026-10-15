import hmac
import json
import os

from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_MAIL_NOTIFICATION
from odoo.addons.sol_laboratory.constants.notifications import BREVO_WEBHOOK_TOKEN


class BrevoWebhook(http.Controller):
    """Brevo transactional webhooks. The token is the bearer token of the webhook auth object."""

    @http.route("/medilab/brevo/webhook", type="http", auth="public", methods=["POST"], csrf=False)
    def webhook(self):
        token = os.environ.get(BREVO_WEBHOOK_TOKEN) or ""
        header = request.httprequest.headers.get("Authorization") or ""
        presented = header[7:] if header.startswith("Bearer ") else ""
        entries = request.env[MODEL_AUDIT_ENTRY]
        if not token or not presented or not hmac.compare_digest(presented, token):
            entries._log_event("error", request.env._("Brevo webhook refused: the token does not match"))
            return request.make_response("Unauthorized", status=401)
        try:
            payload = json.loads(request.httprequest.data or b"{}")
        except ValueError:
            entries._log_event("error", request.env._("Brevo webhook refused: the body is not JSON"))
            return request.make_response("Bad Request", status=400)
        events = payload if isinstance(payload, list) else [payload]
        for event in events:
            if not isinstance(event, dict):
                continue
            notification = request.env[MODEL_MAIL_NOTIFICATION].sudo()._apply_brevo_event(event)
            # Only events about MediLab's own emails are recorded.
            if notification:
                entries._log_event(
                    "integration",
                    request.env._(
                        "Brevo reported %(event)s for %(recipient)s",
                        event=event.get("event"),
                        recipient=notification.res_partner_id.display_name,
                    ),
                    notification.mail_message_id._audit_document(),
                )
        return request.make_response("OK", status=200)
