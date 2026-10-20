from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_NOTIFICATION_PREFERENCE,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, CHANNEL_POPUP, CHANNELS


# Tuỳ Chọn Thông Báo
class NotificationPreference(models.Model):
    _name = MODEL_NOTIFICATION_PREFERENCE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Notification Preference"
    _permission_actions = ("read", "create", "edit", "delete")

    # The Odoo user.
    user_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    # The event.
    event_id = fields.Many2one("mail.message.subtype", required=True, ondelete="cascade", index=True)
    # popup, email or push.
    channel = fields.Selection(
        [(CHANNEL_POPUP, "In the application"), (CHANNEL_EMAIL, "Email"), ("push", "Push")],
        required=True,
    )
    # False when the user turned this channel off. Ignored for a mandatory event.
    enabled = fields.Boolean(default=True)

    _user_event_channel_unique = models.Constraint(
        "UNIQUE(user_id, event_id, channel)",
        "This channel is already chosen for the event.",
    )

    @api.model
    def set_own(self, event, channel, enabled):
        """The signed-in user sets one channel of one event. A mandatory event stays on."""
        if channel not in CHANNELS:
            raise UserError(self.env._("Choose a channel the system sends."))
        if event.mandatory and channel in (CHANNEL_POPUP, CHANNEL_EMAIL) and not enabled:
            raise UserError(self.env._("A mandatory event cannot be turned off."))
        preference = self.sudo().search(
            [("user_id", "=", self.env.user.id), ("event_id", "=", event.id), ("channel", "=", channel)],
            limit=1,
        )
        if preference:
            preference.sudo().write({"enabled": enabled})
            return preference
        return self.sudo().create(
            {"user_id": self.env.user.id, "event_id": event.id, "channel": channel, "enabled": enabled}
        )

    def write(self, vals):
        if not self.env.su and (self.user_id != self.env.user or set(vals) - {"enabled"}):
            raise AccessError(self.env._("You can change only your own channel choices."))
        for preference in self:
            turning_off = vals.get("enabled") is False or (preference.enabled and vals.get("enabled") is False)
            if turning_off and preference.event_id.mandatory and preference.channel in (CHANNEL_POPUP, CHANNEL_EMAIL):
                raise UserError(self.env._("A mandatory event cannot be turned off."))
        if self.env.su:
            return super().write(vals)
        return super(NotificationPreference, self.sudo()).write(vals)
