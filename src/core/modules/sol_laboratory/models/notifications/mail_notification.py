import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_NOTIFICATION

_logger = logging.getLogger(__name__)

STATUS_RANK = {"sent": 1, "deferred": 2, "delivered": 3, "opened": 4}
TERMINAL = {"bounced", "failed"}
EVENT_STATUS = {
    "request": "sent",
    "sent": "sent",
    "deferred": "deferred",
    "delivered": "delivered",
    "opened": "opened",
    "uniqueopened": "opened",
    "unique_opened": "opened",
    "proxy_open": "opened",
    "uniqueproxyopen": "opened",
    "click": "opened",
    "softbounce": "deferred",
    "soft_bounce": "deferred",
    "hardbounce": "bounced",
    "hard_bounce": "bounced",
    "invalid": "bounced",
    "invalid_email": "bounced",
    "blocked": "bounced",
    "error": "failed",
    "spam": "failed",
}


# Thông Báo
class MailNotification(models.Model):
    _inherit = MODEL_MAIL_NOTIFICATION

    # Delivery status Brevo reported: sent, delivered, opened, bounced, failed or deferred.
    brevo_status = fields.Char(readonly=True, copy=False)

    @api.model
    def _cleanup_domain(self, cutoff):
        """The notifications the cleanup job removes with their pushes: MediLab's own, read and posted before the
        cutoff. Notifications of Odoo's chatter stay."""
        return [
            ("is_read", "=", True),
            ("mail_message_id.notification_key", "!=", False),
            ("mail_message_id.date", "<", cutoff),
        ]

    def action_open_document(self):
        """Mark this inbox notification read and open the document it belongs to."""
        self.ensure_one()
        if not self.env.su and self.res_partner_id != self.env.user.partner_id:
            raise AccessError(self.env._("This notification belongs to someone else."))
        self.sudo().write({"is_read": True})
        message = self.mail_message_id
        if not message.model or not message.res_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": message.model,
            "res_id": message.res_id,
            "views": [(False, "form")],
        }

    def _apply_brevo_event(self, event):
        """Record one Brevo event on the notification it names, and nowhere else."""
        status = EVENT_STATUS.get(str(event.get("event") or "").lower().replace(" ", ""))
        email = str(event.get("email") or "").strip().lower()
        if not status or not email:
            return self.browse()
        notification = self._notification_for_brevo(event, email)
        if not notification:
            _logger.info("Brevo event did not match a notification for that recipient")
            return self.browse()
        partner = notification.res_partner_id
        if (partner.email or "").strip().lower() != email:
            return self.browse()
        current = notification.brevo_status
        if current in TERMINAL or (
            current and status not in TERMINAL and STATUS_RANK[status] < STATUS_RANK.get(current, 0)
        ):
            return notification
        if current == status:
            return notification
        values = {"brevo_status": status}
        if status == "bounced":
            values["notification_status"] = "bounce"
            values["failure_type"] = "mail_bounce"
            partner.sudo().write({"email_bounced": True})
        elif status == "failed":
            values["notification_status"] = "exception"
        elif status == "delivered":
            values["notification_status"] = "sent"
        notification.sudo().write(values)
        return notification

    def _notification_for_brevo(self, event, email):
        custom = event.get("X-Mailin-custom") or ""
        if isinstance(custom, str) and custom.startswith("notification:"):
            try:
                notification_id = int(custom.split(":", 1)[1])
            except ValueError:
                return self.browse()
            notification = self.browse(notification_id).exists()
            if notification and (notification.res_partner_id.email or "").strip().lower() == email:
                return notification
            return self.browse()
        message_id = str(event.get("message-id") or event.get("message_id") or "").strip().strip("<>")
        if not message_id:
            return self.browse()
        mails = self.env["mail.mail"].sudo().search([("message_id", "ilike", message_id)])
        notifications = self.sudo().search(
            [
                ("mail_mail_id", "in", mails.ids),
                ("res_partner_id.email", "=ilike", email),
            ]
        )
        return notifications.filtered(lambda item: (item.res_partner_id.email or "").strip().lower() == email)[:1]
