import json
import logging

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.fields import Command
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PERSON,
    MODEL_PUSH_DELIVERY,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP, CHANNEL_PUSH

_logger = logging.getLogger(__name__)


def _apply_preference(preference, event, user, popup, email, push):
    if event.mandatory and preference.channel in (CHANNEL_POPUP, CHANNEL_EMAIL) and not preference.enabled:
        return popup, email, push
    if preference.channel == CHANNEL_POPUP:
        return preference.enabled and bool(user), email, push
    if preference.channel == CHANNEL_EMAIL:
        return popup, preference.enabled, push
    if preference.channel == CHANNEL_PUSH:
        return popup, email, preference.enabled
    return popup, email, push


def _selected_channels(popup, email, push):
    channels = set()
    if popup:
        channels.add(CHANNEL_POPUP)
    if email:
        channels.add(CHANNEL_EMAIL)
    if push:
        channels.add(CHANNEL_PUSH)
    return channels


# Thông Báo
class MailMessage(models.Model):
    _inherit = MODEL_MAIL_MESSAGE

    # Unique key that stops the same notification being created twice.
    notification_key = fields.Char(index=True, copy=False)

    _notification_key_unique = models.UniqueIndex(
        "(notification_key) WHERE notification_key IS NOT NULL",
        "This notification already exists.",
    )

    @api.model
    def raise_event(self, code, document, key, body, subject=None, partners=None, attachments=None):
        """Post one message for this key and queue each channel once.

        The provider is not called here. A second call, including from another transaction
        that loses the unique-key race, returns the message already stored.
        """
        event = self.env["mail.message.subtype"]._event(code)
        if not event:
            return self.browse()
        existing = self.sudo().search([("notification_key", "=", key)], limit=1)
        if existing:
            return existing
        recipients = self._event_partners(event, partners)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                message = self.sudo().create(
                    {
                        "model": document._name,
                        "res_id": document.id,
                        "body": body,
                        "subject": subject or event.name,
                        "message_type": "notification",
                        "subtype_id": event.id,
                        "notification_key": key,
                        "attachment_ids": [Command.link(attachment.id) for attachment in attachments]
                        if attachments
                        else [],
                    }
                )
                message._deliver(event, recipients)
        except IntegrityError:
            return self.sudo().search([("notification_key", "=", key)], limit=1)
        return message

    def _deliver(self, event, partners):
        self.ensure_one()
        for partner in partners:
            channels = self._channels_for(partner, event)
            if not channels:
                continue
            notification = self._notification_for(partner, CHANNEL_POPUP in channels)
            if CHANNEL_EMAIL in channels:
                self._queue_email(notification, partner, event)
            elif CHANNEL_EMAIL not in channels and not partner.email:
                _logger.warning("Notification %s has no email address for partner %s", event.code, partner.id)
            if CHANNEL_PUSH in channels:
                self._queue_pushes(notification, partner)
            if CHANNEL_POPUP in channels:
                self._popup(partner)

    @api.model
    def _event_partners(self, event, partners):
        collected = partners or self.env["res.partner"]
        recipients = self.env[MODEL_NOTIFICATION_EVENT_RECIPIENT].sudo().search([("event_id", "=", event.id)])
        people = self.env[MODEL_PERSON].sudo()
        for recipient in recipients:
            if recipient.role_id:
                people |= recipient.role_id.person_ids
            if recipient.department_id:
                people |= self.env[MODEL_PERSON].sudo().search([("department_id", "=", recipient.department_id.id)])
        collected |= people.user_id.partner_id
        return collected

    def _channels_for(self, partner, event):
        user = partner.user_ids[:1]
        popup, email, push = self._preferred_channels(user, event)
        if event.mandatory:
            popup = bool(user) and (popup or user.notification_type == "inbox")
            email = True
        if partner.email_bounced or not partner.email:
            if email and not partner.email:
                _logger.warning("Notification %s has no email address for partner %s", event.code, partner.id)
            email = False
        return _selected_channels(popup, email, push)

    def _preferred_channels(self, user, event):
        popup = bool(user) and user.notification_type == "inbox"
        email = (not user) or user.notification_type == "email"
        push = False
        if not user:
            return popup, email, push
        preferences = (
            self.env[MODEL_NOTIFICATION_PREFERENCE]
            .sudo()
            .search([("user_id", "=", user.id), ("event_id", "=", event.id)])
        )
        for preference in preferences:
            popup, email, push = _apply_preference(preference, event, user, popup, email, push)
        return popup, email, push

    def _notification_for(self, partner, popup):
        self.ensure_one()
        notification = (
            self.env[MODEL_MAIL_NOTIFICATION]
            .sudo()
            .search(
                [("mail_message_id", "=", self.id), ("res_partner_id", "=", partner.id)],
                limit=1,
            )
        )
        if notification:
            return notification
        return (
            self.env[MODEL_MAIL_NOTIFICATION]
            .sudo()
            .create(
                {
                    "mail_message_id": self.id,
                    "res_partner_id": partner.id,
                    "notification_type": "inbox" if popup else "email",
                    "notification_status": "sent" if popup else "ready",
                }
            )
        )

    def _popup(self, partner):
        user = partner.user_ids[:1]
        if not user or user.share:
            return
        user._bus_send("mail.message/inbox", {"message_id": self.id})

    def _queue_email(self, notification, partner, event):
        if notification.mail_mail_id:
            return
        mail = (
            self.env["mail.mail"]
            .sudo()
            .create(
                {
                    "subject": self.subject or event.name,
                    "body_html": self.body or "",
                    "email_from": self.env.company.email or self.env.user.email or "notifications@localhost",
                    "email_to": partner.email,
                    "recipient_ids": [Command.link(partner.id)],
                    "mail_message_id": self.id,
                    "auto_delete": False,
                    "state": "outgoing",
                    "headers": json.dumps({"X-Mailin-custom": f"notification:{notification.id}"}),
                    "attachment_ids": [Command.link(attachment.id) for attachment in self.attachment_ids],
                }
            )
        )
        notification.sudo().write({"mail_mail_id": mail.id})
        self.env[MODEL_SCHEDULED_JOB].queue("notifications.email", f"mail:{mail.id}", document=mail)

    def _queue_pushes(self, notification, partner):
        user = partner.user_ids[:1]
        if not user:
            return
        devices = self.env[MODEL_MOBILE_DEVICE].sudo().search([("user_id", "=", user.id), ("active", "=", True)])
        deliveries = self.env[MODEL_PUSH_DELIVERY].sudo()
        for device in devices:
            existing = deliveries.search(
                [("notification_id", "=", notification.id), ("mobile_device_id", "=", device.id)],
                limit=1,
            )
            if existing:
                delivery = existing
            else:
                try:
                    with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                        delivery = deliveries.create(
                            {"notification_id": notification.id, "mobile_device_id": device.id, "status": "pending"}
                        )
                except IntegrityError:
                    delivery = deliveries.search(
                        [("notification_id", "=", notification.id), ("mobile_device_id", "=", device.id)],
                        limit=1,
                    )
            if delivery and delivery.status == "pending":
                self.env[MODEL_SCHEDULED_JOB].queue("notifications.push", f"delivery:{delivery.id}", document=delivery)

    def _audit_document(self):
        """The document the message is posted on, which the entries of its emails and pushes are written on."""
        self.ensure_one()
        if not self.res_id or self.model not in self.env:
            return None
        return self.env[self.model].sudo().browse(self.res_id).exists() or None
