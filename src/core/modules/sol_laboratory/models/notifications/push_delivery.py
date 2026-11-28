from typing import TYPE_CHECKING

from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import mute_logger

from odoo.addons.sol_laboratory.constants.medilab_mobile import MESSAGE_EVENT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DISCUSS_CHANNEL,
    MODEL_LOCK_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PUSH_DELIVERY,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_MESSAGE_MENTION, PUSH_JOB
from odoo.addons.sol_laboratory.services.document_code import document_code
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_push_delivery as PushDeliveryBase
else:
    PushDeliveryBase = object


# Đẩy Thông Báo
class PushDelivery(models.Model, PushDeliveryBase):
    _name = MODEL_PUSH_DELIVERY
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN]
    _description = "Push Delivery"
    _order = "id"
    _permission_actions = ("read", "create", "edit")

    if not TYPE_CHECKING:
        # The notification pushed; empty for a message.
        notification_id = fields.Many2one(MODEL_MAIL_NOTIFICATION, ondelete="cascade", index=True)
        # The message pushed, of a conversation or mentioning the person; empty for a notification.
        message_id = fields.Many2one(MODEL_MAIL_MESSAGE, ondelete="cascade", index=True)
        # The mobile device pushed to.
        mobile_device_id = fields.Many2one(MODEL_MOBILE_DEVICE, required=True, ondelete="cascade", index=True)
        # pending, sent, failed or skipped.
        status = fields.Selection(
            [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("skipped", "Skipped")],
            required=True,
            default="pending",
            index=True,
        )
        # When it was sent.
        sent_at = fields.Datetime(readonly=True)
        # Error Firebase returned on the last failed attempt.
        error = fields.Text()

    _notification_device_unique = models.Constraint(
        "UNIQUE(notification_id, mobile_device_id)",
        "This notification is already pushed to the device.",
    )
    _message_device_unique = models.Constraint(
        "UNIQUE(message_id, mobile_device_id)",
        "This message is already pushed to the device.",
    )
    _notification_or_message = models.Constraint(
        "CHECK((notification_id IS NULL) <> (message_id IS NULL))",
        "A push is of a notification or of a message.",
    )

    @api.model
    def _queue(self, values):
        """The push of the values, created once even by two transactions at once, and queued for the push job while it
        is pending; no push once it was sent or skipped."""
        domain = Domain.AND(Domain(name, "=", value) for name, value in values.items())
        delivery = self.search(domain, limit=1)
        if not delivery:
            try:
                with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                    delivery = self.create({**values, "status": "pending"})
            except IntegrityError:
                delivery = self.search(domain, limit=1)
        if delivery.status != "pending":
            return self.browse()
        self.env[MODEL_SCHEDULED_JOB].queue(PUSH_JOB, f"delivery:{delivery.id}", document=delivery)
        return delivery

    def _run_now(self):
        """Run the push job at once instead of waiting for its next run."""
        self.env[MODEL_SCHEDULED_JOB].sudo()._by_key(PUSH_JOB).cron_id._trigger()

    def _message(self):
        """The message pushed: the message itself, or the message of the notification."""
        self.ensure_one()
        return self.message_id or self.notification_id.mail_message_id

    def _push_message(self):
        """The title, body and data of the push. The title is the event's name in the person's language and the body the
        document's code; the data name the event, the document and its code. A conversation message names its
        conversation and its author. A message's or a notification's own text, the document's name and its other
        fields are never pushed, so a push never names a customer."""
        self.ensure_one()
        message = self._message().sudo()
        user = self.mobile_device_id.sudo().user_id
        if self.message_id and message.model == MODEL_DISCUSS_CHANNEL:
            channel = self.env[MODEL_DISCUSS_CHANNEL].sudo().browse(message.res_id)
            data = {"event": MESSAGE_EVENT, "model": MODEL_DISCUSS_CHANNEL, "id": str(channel.id)}
            return channel._mobile_name(user), message.author_id.name or "", data
        subtype = self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_MESSAGE_MENTION) if self.message_id else None
        event = (subtype or message.subtype_id).with_context(lang=user.lang or self.env.lang)
        code = ""
        if message.model and message.res_id and message.model in self.env:
            code = document_code(dynamic_model(self.env, message.model).browse(message.res_id))
        data = {
            "event": event.code or "",
            "model": message.model or "",
            "id": str(message.res_id or ""),
            "code": code,
        }
        return event.name or "", code, data
