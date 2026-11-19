from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_ATTACHMENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
)
from odoo.addons.sol_laboratory.services.laboratory_api import api_datetime

if TYPE_CHECKING:
    from medilab_model_types import Model_ir_attachment as IrAttachmentMobileBase
else:
    IrAttachmentMobileBase = object


# Tệp Đính Kèm: a photo Medilab Mobile attaches to a sample, created once per Idempotency-Key of its phone.
class IrAttachmentMobile(models.Model, IrAttachmentMobileBase):
    _name = MODEL_IR_ATTACHMENT
    _inherit = [MODEL_IR_ATTACHMENT, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "created_by_device_id"

    if not TYPE_CHECKING:
        # The phone the photo was taken on; empty for a file attached on the web.
        created_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(created_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already sent a photo with this Idempotency-Key.",
    )

    def _mobile_values(self):
        """The photos as Medilab Mobile lists them. Who took a photo is read with full rights, as the web's chatter
        shows it."""
        return [
            {
                "id": photo.id,
                "name": photo.name,
                "mimetype": photo.mimetype or "",
                "created_at": api_datetime(photo.create_date),
                "created_by": photo.sudo().create_uid.name or "",
            }
            for photo in self
        ]
