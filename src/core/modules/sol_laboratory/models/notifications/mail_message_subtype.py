from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
)


# Loại Thông Báo
class MailMessageSubtype(models.Model):
    _name = MODEL_MAIL_MESSAGE_SUBTYPE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_MAIL_MESSAGE_SUBTYPE]
    _audit_children = ("recipient_ids",)

    # Unique code of the event, such as task.reminder.
    code = fields.Char(index=True)
    # True when people cannot turn the event off.
    mandatory = fields.Boolean()
    # False when the administrator turned the event off. Ignored when it is mandatory.
    enabled = fields.Boolean(default=True)
    # Roles and departments notified of this event.
    recipient_ids = fields.One2many(MODEL_NOTIFICATION_EVENT_RECIPIENT, "event_id", string="Recipients")

    _code_unique = models.UniqueIndex("(code) WHERE code IS NOT NULL", "An event with this code already exists.")

    def write(self, vals):
        if vals.get("enabled") is False and any(event.mandatory for event in self):
            raise UserError(self.env._("A mandatory event cannot be turned off."))
        return super().write(vals)

    @api.model
    def _event(self, code):
        event = self.sudo().search([("code", "=", code)], limit=1)
        if not event or (not event.enabled and not event.mandatory):
            return self.browse()
        return event
