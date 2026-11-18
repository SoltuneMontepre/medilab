from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACT_DISPATCH_HANDOVER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontract_dispatch_handover as HandoverBase
else:
    HandoverBase = object


# Bàn Giao Phiếu Gửi Thầu Phụ
class SubcontractDispatchHandover(models.TransientModel, HandoverBase):
    _name = MODEL_SUBCONTRACT_DISPATCH_HANDOVER
    _description = "Hand Over a Subcontract Dispatch"

    if not TYPE_CHECKING:
        # The draft dispatch the sample delivery staff take.
        dispatch_id = fields.Many2one(MODEL_SUBCONTRACT_DISPATCH, required=True, ondelete="cascade")
        # The delivery service the samples are handed to; empty when the sample delivery staff carry them.
        delivery_service = fields.Char()
        # The tracking number the delivery service gave.
        tracking_number = fields.Char()

    def action_hand_over(self):
        self.ensure_one()
        self.dispatch_id._hand_over(self.delivery_service, self.tracking_number)
