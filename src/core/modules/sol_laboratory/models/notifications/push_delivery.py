from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LOCK_MIXIN,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PUSH_DELIVERY,
)

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
        # The notification pushed.
        notification_id = fields.Many2one(MODEL_MAIL_NOTIFICATION, required=True, ondelete="cascade", index=True)
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
