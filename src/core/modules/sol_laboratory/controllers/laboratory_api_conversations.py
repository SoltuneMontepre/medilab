from datetime import datetime

from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_DISCUSS_CHANNEL
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.mobile_messages import message_page, people, post_from_phone


class LaboratoryApiConversations(http.Controller):
    """The person's direct and group conversations on Medilab Mobile, the same as Discuss on the web."""

    @laboratory_api_route("/conversations", ["GET"], "listConversations", permission=False)
    def list_conversations(self, device, _body):
        return {"conversations": device.env[MODEL_DISCUSS_CHANNEL]._mobile_list()}

    @laboratory_api_route("/conversations", ["POST"], "openConversation", permission=False)
    def open_conversation(self, device, body, idempotency_key=None):
        channel = device.env[MODEL_DISCUSS_CHANNEL]._open_from_phone(device, body, idempotency_key)
        return channel._mobile_values()[0]

    @laboratory_api_route(
        "/conversations/<int:channel_id>/messages", ["GET"], "listConversationMessages", permission=False
    )
    def list_messages(self, device, _body, channel_id, before=None, after=None, limit=None):
        channel = device.env[MODEL_DISCUSS_CHANNEL]._mobile_conversation(channel_id)
        return message_page(channel, before, after, limit)

    @laboratory_api_route(
        "/conversations/<int:channel_id>/messages", ["POST"], "postConversationMessage", permission=False
    )
    def post_message(self, device, body, channel_id, idempotency_key=None):
        channel = device.env[MODEL_DISCUSS_CHANNEL]._mobile_conversation(channel_id)
        message = post_from_phone(channel, device, body, idempotency_key, "mail.mt_comment")
        return message._mobile_values()[0]

    @laboratory_api_route("/conversations/<int:channel_id>/seen", ["POST"], "markConversationSeen", permission=False)
    def mark_seen(self, device, body, channel_id):
        channel = device.env[MODEL_DISCUSS_CHANNEL]._mobile_conversation(channel_id)
        channel.self_member_id._mark_as_read(body["message_id"])

    @laboratory_api_route("/conversations/<int:channel_id>/mute", ["PUT"], "muteConversation", permission=False)
    def mute(self, device, body, channel_id):
        channel = device.env[MODEL_DISCUSS_CHANNEL]._mobile_conversation(channel_id)
        member = channel.self_member_id
        # Muted until the person unmutes it, as Discuss on the web mutes it.
        member.mute_until_dt = datetime.max if body["muted"] else False
        member._set_cron_for_unmute()
        return channel._mobile_values()[0]

    @laboratory_api_route("/people", ["GET"], "searchPeople", permission=False)
    def search_people(self, device, _body, q=""):
        return people(device.env, q)
