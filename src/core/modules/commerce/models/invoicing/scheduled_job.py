from odoo import models

from odoo.addons.commerce.services.payos_client import PayosClient
from odoo.addons.laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.laboratory.models.system.scheduled_job import PermanentJobError


class PayosNotConfigured(Exception):
    """The credentials left the environment; the item is retried until an administrator restores them."""


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _handle_payos_calls(self, item):
        # Replays a PayOS call that failed during an outage: the payload names the call, the document is the link.
        link = self._payment_link(item)
        call = (item.payload or {}).get("call")
        if call == "create":
            link._replay_creation()
        elif call == "cancel":
            link._replay_cancel()
        else:
            raise PermanentJobError(f"Unknown PayOS call {call!r}")

    def _handle_payos_poll(self, item):
        return self._payment_link(item)._poll()

    @staticmethod
    def _payment_link(item):
        # No call leaves the server without credentials, so an unconfigured server never calls PayOS with empty keys.
        if not PayosClient().is_configured():
            raise PayosNotConfigured(
                "PayOS credentials are not configured: set PAYOS_CLIENT_ID, PAYOS_API_KEY and PAYOS_CHECKSUM_KEY"
            )
        link = item._document()
        if link is None or not link.exists():
            raise PermanentJobError("The payment link of this item no longer exists")
        return link
