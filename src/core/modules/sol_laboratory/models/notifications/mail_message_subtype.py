from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
)
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_message_subtype as MailMessageSubtypeBase
else:
    MailMessageSubtypeBase = object


# Loại Thông Báo
class MailMessageSubtype(models.Model, MailMessageSubtypeBase):
    _name = MODEL_MAIL_MESSAGE_SUBTYPE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_MAIL_MESSAGE_SUBTYPE]
    _audit_children = ("recipient_ids",)

    if not TYPE_CHECKING:
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
        required = self.filtered("mandatory")
        disabling = "enabled" in vals and not vals["enabled"]
        changes_rule = ("mandatory" in vals and not vals["mandatory"]) or (
            "code" in vals and any(event.code != vals["code"] for event in required)
        )
        if required and (disabling or (changes_rule and not self.env.su)):
            raise UserError(self.env._("A mandatory event cannot be turned off."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_mandatory_events(self):
        if not self.env.su and any(event.mandatory for event in self):
            raise UserError(self.env._("A mandatory event cannot be turned off."))

    def _documents_readable(self):
        """Whether the current user may read the kind of document the event is about, so may open what it notifies them
        of; an event about no kind of document is."""
        self.ensure_one()
        model = self.sudo().res_model
        return not model or (model in self.env and dynamic_model(self.env, model).has_access("read"))

    @api.model
    def _event(self, code):
        event = self.sudo().search([("code", "=", code)], limit=1)
        if not event or (not event.enabled and not event.mandatory):
            return self.browse()
        return event
