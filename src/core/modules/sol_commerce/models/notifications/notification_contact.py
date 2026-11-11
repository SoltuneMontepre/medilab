from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_commerce.constants.models import MODEL_NOTIFICATION_CONTACT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_MAIL_MESSAGE_SUBTYPE,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_notification_contact as NotificationContactBase
else:
    NotificationContactBase = object


# Người Nhận Thông Báo Của Khách Hàng
class NotificationContact(models.Model, NotificationContactBase):
    _name = MODEL_NOTIFICATION_CONTACT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Customer Notification Contact"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The business customer.
        partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade", index=True)
        # The event.
        event_id = fields.Many2one(MODEL_MAIL_MESSAGE_SUBTYPE, required=True, ondelete="cascade", index=True)
        # The contact of the business who receives the event instead of the contact the document names.
        contact_id = fields.Many2one("res.partner", required=True, ondelete="cascade")

    _partner_event_unique = models.Constraint(
        "UNIQUE(partner_id, event_id)",
        "This event already has a contact.",
    )

    @api.constrains("partner_id", "contact_id")
    def _check_contact_belongs_to_business(self):
        for route in self:
            if route.contact_id.parent_id != route.partner_id:
                raise ValidationError(self.env._("Choose a contact of the company."))

    @api.model
    def set_own(self, event, contact):
        """The signed-in customer's business sends one event to one of its contacts; an empty contact clears it."""
        business = self.env.user.partner_id.commercial_partner_id
        route = self.sudo().search([("partner_id", "=", business.id), ("event_id", "=", event.id)])
        if not contact:
            route.unlink()
            return route
        if contact.parent_id != business:
            raise UserError(self.env._("Choose a contact of the company."))
        if route:
            route.write({"contact_id": contact.id})
            return route
        return self.sudo().create({"partner_id": business.id, "event_id": event.id, "contact_id": contact.id})
