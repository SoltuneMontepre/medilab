from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.tools import html2plaintext

from odoo.addons.sol_laboratory.constants.medilab_mobile import CONVERSATION_TYPES
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DISCUSS_CHANNEL,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_MOBILE_DEVICE,
    MODEL_PUSH_DELIVERY,
    MODEL_RES_PARTNER,
)
from odoo.addons.sol_laboratory.constants.notifications import (
    CHANNEL_EMAIL,
    CHANNEL_POPUP,
    CHANNEL_PUSH,
    EVENT_MESSAGE_MENTION,
)
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_message as MailMessageConversationBase
else:
    MailMessageConversationBase = object

# The Odoo notification of each channel a mention reaches in the application or by email.
ODOO_CHANNELS = {CHANNEL_POPUP: "inbox", CHANNEL_EMAIL: "email"}


# Tin Nhắn: a message of a conversation or of a document's chatter, which a phone posts once per Idempotency-Key; its
# mentions notify on each channel the people keep on, and it is pushed to the phones of the people it reaches.
class MailMessageConversation(models.Model, MailMessageConversationBase):
    _name = MODEL_MAIL_MESSAGE
    _inherit = [MODEL_MAIL_MESSAGE, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "posted_by_device_id"

    if not TYPE_CHECKING:
        # The phone the message or the note was posted from; empty for one posted on the web.
        posted_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(posted_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already posted a message with this Idempotency-Key.",
    )

    def _mobile_values(self):
        """The messages as Medilab Mobile shows them: their author, their text, whether they are notes and their files.
        Authors' names are read with full rights, as the web's chatter shows them."""
        note = self.env.ref("mail.mt_note")
        partner = self.env.user.partner_id
        return [
            {
                "id": message.id,
                "author": message.author_id.sudo().name or "",
                "mine": message.author_id == partner,
                "date": api_datetime(message.date),
                "text": html2plaintext(message.body or "", include_references=False),
                "note": message.subtype_id == note,
                "attachments": [
                    {"id": attachment.id, "name": attachment.name or "", "mimetype": attachment.mimetype or ""}
                    for attachment in message.attachment_ids
                ],
            }
            for message in self
        ]

    def _mention_event(self):
        """The event of a mention, or none when the administrator turned it off."""
        if self.message_type != "comment":
            return self.env[MODEL_MAIL_MESSAGE_SUBTYPE]
        return self.env[MODEL_MAIL_MESSAGE_SUBTYPE]._event(EVENT_MESSAGE_MENTION)

    def _mentioned(self):
        """The people of the laboratory the message mentions, except its author."""
        return (self.partner_ids - self.author_id).filtered(
            lambda partner: any(not user.share for user in partner.user_ids)
        )

    def _mention_recipients(self, recipients):
        """The recipients Odoo notifies, once each person the message mentions gets it in the application or by email
        as they chose for mentions, or not at all when they turned both off; a follower keeps Odoo's notification."""
        self.ensure_one()
        event = self._mention_event()
        if not event:
            return recipients
        mentioned = self._mentioned()
        kept = []
        for recipient in recipients:
            if recipient["id"] in mentioned.ids and recipient["uid"] and not recipient["ushare"]:
                channels = self._channels_for(self.env[MODEL_RES_PARTNER].browse(recipient["id"]), event)
                odoo_channel = next((ODOO_CHANNELS[name] for name in ODOO_CHANNELS if name in channels), None)
                if odoo_channel:
                    recipient = {**recipient, "notif": odoo_channel}
                elif not recipient.get("is_follower"):
                    continue
            kept.append(recipient)
        return kept

    def _notify_mentions_and_phones(self, thread):
        """Once Odoo notified the message: email the people it mentions who keep both the application and email on, and
        push it to the phones of the people it mentions and, in a direct or group conversation, of its members except its
        author and those who muted it."""
        self.ensure_one()
        if self.message_type != "comment":
            return
        event = self._mention_event()
        pushed = self.env[MODEL_RES_PARTNER]
        for partner in self._mentioned() if event else pushed:
            channels = self._channels_for(partner, event)
            if {CHANNEL_POPUP, CHANNEL_EMAIL} <= channels:
                self._queue_email(self._notification_for(partner, popup=True), partner, event)
            if CHANNEL_PUSH in channels:
                pushed |= partner
        if thread._name == MODEL_DISCUSS_CHANNEL and thread.channel_type in CONVERSATION_TYPES:
            members = thread.sudo().channel_member_ids.filtered(lambda member: not member._is_muted())
            pushed |= members.partner_id - self.author_id
        self._queue_message_pushes(pushed)

    def _queue_message_pushes(self, partners):
        """Push the message to the phones of the people of the laboratory, and run the push job at once."""
        devices = self.env[MODEL_MOBILE_DEVICE]
        for user in partners.user_ids.filtered(lambda user: not user.share):
            devices |= devices._push_tokens(user)
        deliveries = self.env[MODEL_PUSH_DELIVERY].sudo()
        for device in devices:
            deliveries |= deliveries._queue({"message_id": self.id, "mobile_device_id": device.id})
        if deliveries:
            deliveries._run_now()
