from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_IDEMPOTENCY_MIXIN,
    MODEL_MAIL_MESSAGE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_message as SupportAnswerMessageBase
else:
    SupportAnswerMessageBase = object


# Tin Nhắn: a support answer a phone posts once per Idempotency-Key.
class SupportAnswerMessage(models.Model, SupportAnswerMessageBase):
    _name = MODEL_MAIL_MESSAGE
    _inherit = [MODEL_MAIL_MESSAGE, MODEL_LABORATORY_IDEMPOTENCY_MIXIN]
    _idempotency_device_field = "posted_by_device_id"

    if not TYPE_CHECKING:
        # The phone the message was posted from with an Idempotency-Key; empty for any other message.
        posted_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, readonly=True, copy=False, ondelete="set null")

    _device_idempotency_key_unique = models.UniqueIndex(
        "(posted_by_device_id, idempotency_key) WHERE idempotency_key IS NOT NULL",
        "This phone already posted a message with this Idempotency-Key.",
    )
