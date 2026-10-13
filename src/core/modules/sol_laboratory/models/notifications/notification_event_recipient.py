from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_NOTIFICATION_EVENT_RECIPIENT,
    MODEL_PERMISSION_MIXIN,
    MODEL_ROLE,
)


# Người nhận của một loại thông báo: một vai trò hoặc một phòng.
class NotificationEventRecipient(models.Model):
    _name = MODEL_NOTIFICATION_EVENT_RECIPIENT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Notification Event Recipient"
    _permission_actions = ("read", "create", "edit", "delete")

    # The event these people are notified of.
    event_id = fields.Many2one("mail.message.subtype", required=True, ondelete="cascade", index=True)
    # A role whose holders are notified.
    role_id = fields.Many2one(MODEL_ROLE, ondelete="cascade")
    # A department whose people are notified.
    department_id = fields.Many2one(MODEL_DEPARTMENT, ondelete="cascade")

    @api.constrains("role_id", "department_id")
    def _check_one_target(self):
        for recipient in self:
            if bool(recipient.role_id) == bool(recipient.department_id):
                raise ValidationError(self.env._("Choose a role or a department, not both and not neither."))
