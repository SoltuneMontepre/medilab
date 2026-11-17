from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST
from odoo.addons.sol_laboratory.constants.medilab_mobile import CONVERSATION_TYPES
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DISCUSS_CHANNEL,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_MAIL_MESSAGE,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.mobile_documents import not_found
from odoo.addons.sol_laboratory.services.mobile_messages import internal_users
from odoo.addons.sol_laboratory.services.record_id import persisted_id

if TYPE_CHECKING:
    from medilab_model_types import Model_discuss_channel as DiscussChannelBase
else:
    DiscussChannelBase = object


# Hội Thoại: the person's direct and group conversations on Medilab Mobile, read and changed with their rights; a phone
# creates a group once per Idempotency-Key.
class DiscussChannel(models.Model, DiscussChannelBase):
    _name = MODEL_DISCUSS_CHANNEL
    _inherit = [MODEL_DISCUSS_CHANNEL, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "created_by_device_id"

    if not TYPE_CHECKING:
        # The phone the group was created on; empty for a conversation opened on the web.
        created_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(created_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already created a conversation with this Idempotency-Key.",
    )

    def _notify_get_recipients(self, message, **kwargs):
        return message._mention_recipients(super()._notify_get_recipients(message, **kwargs))

    @api.model
    def _mobile_list(self):
        """The person's direct and group conversations, the latest message first."""
        channels = self.search(
            Domain("channel_type", "in", CONVERSATION_TYPES) & Domain("self_member_id", "!=", False),
            order="last_interest_dt desc, id desc",
        )
        return channels._mobile_values()

    @api.model
    def _open_from_phone(self, device, body, key):
        """Open the direct conversation with one person, or create a group with a name and members once per
        Idempotency-Key, as Discuss on the web does."""
        if body.get("person_id"):
            person = internal_users(self.env, [body["person_id"]])
            return self._get_or_create_chat(person.partner_id.ids)
        created = self._created_with_key(device, key)
        if created:
            return created
        members = internal_users(self.env, body.get("member_ids"))
        if not members:
            raise LaboratoryFileError(INVALID_REQUEST, self.env._("Choose the people of the conversation."))
        channel = self._create_group(members | self.env.user, name=(body.get("name") or "").strip())
        channel = self.env[MODEL_DISCUSS_CHANNEL].browse(persisted_id(channel))
        channel._keep_key(device, key)
        return channel

    @api.model
    def _mobile_conversation(self, channel_id):
        """The person's conversation; one they are not a member of is not found."""
        channel = self.search(
            Domain("id", "=", channel_id)
            & Domain("channel_type", "in", CONVERSATION_TYPES)
            & Domain("self_member_id", "!=", False)
        )
        if not channel:
            raise not_found(self.env)
        return channel

    def _mobile_values(self):
        """The conversations as Medilab Mobile lists them: their unread count, whether the person muted them, their
        members and their last message. Members' names are read with full rights, as Discuss shows them."""
        messages = self.env[MODEL_MAIL_MESSAGE]
        values = []
        for channel in self:
            member = channel.self_member_id
            last = messages.search(
                [("model", "=", MODEL_DISCUSS_CHANNEL), ("res_id", "=", channel.id), ("message_type", "=", "comment")],
                order="id desc",
                limit=1,
            )
            users = channel.sudo().channel_member_ids.partner_id.user_ids.filtered(lambda user: not user.share)
            values.append(
                {
                    "id": channel.id,
                    "type": channel.channel_type,
                    "name": channel._mobile_name(self.env.user),
                    "unread": member.message_unread_counter,
                    "muted": member._is_muted(),
                    "members": [{"id": user.id, "name": user.name} for user in users],
                    "last_message": last._mobile_values()[0] if last else None,
                }
            )
        return values

    def _mobile_name(self, user):
        """The conversation's name as the person sees it: a group's name, or the other people's names."""
        self.ensure_one()
        channel = self.sudo()
        if channel.channel_type == "group" and channel.name:
            return channel.name
        others = channel.channel_member_ids.partner_id - user.partner_id
        return ", ".join(others.mapped("name")) or channel.name or ""
