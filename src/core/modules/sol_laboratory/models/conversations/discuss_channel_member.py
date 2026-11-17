from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_DISCUSS_CHANNEL_MEMBER

if TYPE_CHECKING:
    from medilab_model_types import Model_discuss_channel_member as DiscussChannelMemberBase
else:
    DiscussChannelMemberBase = object


# Thành Viên Hội Thoại
class DiscussChannelMember(models.Model, DiscussChannelMemberBase):
    _inherit = MODEL_DISCUSS_CHANNEL_MEMBER

    @api.constrains("partner_id", "guest_id")
    def _check_internal_member(self):
        """Only a person with an internal user takes part in a conversation, on the web and the phone alike, so a
        customer, a subcontractor or a guest never joins one."""
        for member in self:
            users = member.partner_id.with_context(active_test=False).user_ids
            if not users.filtered(lambda user: not user.share):
                raise ValidationError(
                    self.env._(
                        "Only people of the laboratory take part in conversations, so %s cannot be added.",
                        member.partner_id.display_name or member.guest_id.name or "",
                    )
                )

    def _is_muted(self):
        """Whether the member muted the conversation, so its messages are not pushed to them."""
        self.ensure_one()
        return bool(self.mute_until_dt) and self.mute_until_dt > fields.Datetime.now()
