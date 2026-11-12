import logging
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_MAIL_NOTIFICATION
from odoo.addons.sol_laboratory.services.document_code import document_code
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_notification as MailNotificationBase
else:
    MailNotificationBase = object

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
class MailNotification(models.Model, MailNotificationBase):
    _inherit = MODEL_MAIL_NOTIFICATION

    if not TYPE_CHECKING:
        # Delivery status Brevo reported: sent, delivered, opened, bounced, failed or deferred.
        brevo_status = fields.Char(readonly=True, copy=False)
        # True when the recipient sees this notice in the customer portal, whatever happens to its email. It is kept
        # apart from notification_type, which Odoo reads as the channel.
        portal_visible = fields.Boolean(default=False, copy=False)
        # When the recipient first opened the notice in the portal; empty until then. It is kept apart from is_read,
        # which belongs to Odoo's inbox.
        portal_seen_at = fields.Datetime(readonly=True, copy=False)

    @api.model
    def _cleanup_domain(self, cutoff):
        """The notifications the cleanup job removes with their pushes: MediLab's own, read and posted before the
        cutoff. Notifications of Odoo's chatter stay."""
        return [
            ("is_read", "=", True),
            ("mail_message_id.notification_key", "!=", False),
            ("mail_message_id.date", "<", cutoff),
        ]

    @api.model
    def _portal_domain(self, user):
        """The notices the signed-in portal user may read: those addressed to the user's own contact, shown in the
        portal or, as before, delivered to the inbox. Another contact of the same business, or another customer, is
        never included."""
        return Domain("res_partner_id", "=", user.partner_id.id) & (
            Domain("portal_visible", "=", True) | Domain("notification_type", "=", "inbox")
        )

    def _portal_open(self):
        """Record the first time the recipient opened the notice; a later open leaves that time as it is.

        The condition is in the statement because two opens at once must not both write."""
        self.ensure_one()
        self.flush_recordset(["portal_seen_at"])
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET portal_seen_at = %s WHERE id = %s AND portal_seen_at IS NULL",
                SQL.identifier(self._table),
                fields.Datetime.now(),
                self.id,
            )
        )
        self.invalidate_recordset(["portal_seen_at"])

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

    @api.model
    def _inbox_domain(self):
        """The signed-in user's inbox notifications, which the web's inbox shows."""
        return Domain("res_partner_id", "=", self.env.user.partner_id.id) & Domain("notification_type", "=", "inbox")

    @api.model
    def _inbox_after(self, after, limit):
        """The signed-in user's inbox notifications, unread first, then newest first, that come after the notification
        after, the last one the app has; from the first one when after is 0."""
        domain = self._inbox_domain()
        if after:
            last = self.sudo().search(domain & Domain("id", "=", after))
            if not last:
                raise MissingError(self.env._("This notification is no longer in your inbox."))
            older = Domain("id", "<", last.id)
            if last.is_read:
                domain &= Domain("is_read", "=", True) & older
            else:
                domain &= Domain("is_read", "=", True) | (Domain("is_read", "=", False) & older)
        return self.sudo().search(domain, order="is_read, id desc", limit=limit)

    @api.model
    def _mark_inbox_read(self, message_id):
        """Mark the signed-in user's notification of the message read, as opening it in the web's inbox does."""
        if not self.sudo().search_count(self._inbox_domain() & Domain("mail_message_id", "=", message_id), limit=1):
            raise MissingError(self.env._("This notification is no longer in your inbox."))
        self.env[MODEL_MAIL_MESSAGE].browse(message_id).set_message_done()

    def _mobile_values(self):
        """The notification as Medilab Mobile lists it: its event and the event's name, its date, its document and
        whether it is read. Its text is left out, as from a push: the app shows the document read with the person's
        rights."""
        self.ensure_one()
        message = self.sudo().mail_message_id
        event = message.subtype_id.with_env(self.env)
        document = None
        if message.model and message.res_id:
            record = (
                dynamic_model(self.env, message.model).browse(message.res_id) if message.model in self.env else None
            )
            document = {
                "model": message.model,
                "id": message.res_id,
                "code": document_code(record) if record is not None else "",
            }
        return {
            "id": message.id,
            "event": event.code or None,
            "title": event.name or "",
            "date": api_datetime(message.date),
            "read": self.is_read,
            "document": document,
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
        if ((partner.email or "").strip().lower()) != email:
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
            if notification and ((notification.res_partner_id.email or "").strip().lower()) == email:
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
        return notifications.filtered(lambda item: ((item.res_partner_id.email or "").strip().lower()) == email)[:1]
