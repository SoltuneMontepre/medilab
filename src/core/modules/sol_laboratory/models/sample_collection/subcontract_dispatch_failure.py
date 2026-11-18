from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_SUBCONTRACT_DISPATCH_FAILURE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontract_dispatch_failure as FailureBase
else:
    FailureBase = object


# Giao Phiếu Gửi Thầu Phụ Thất Bại
class SubcontractDispatchFailure(models.TransientModel, FailureBase):
    _name = MODEL_SUBCONTRACT_DISPATCH_FAILURE
    _description = "Failed Delivery of a Subcontract Dispatch"

    if not TYPE_CHECKING:
        # The sent dispatch whose delivery failed.
        dispatch_id = fields.Many2one(MODEL_SUBCONTRACT_DISPATCH, required=True, ondelete="cascade")
        # Why the delivery failed.
        reason = fields.Text(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.dispatch_id._report_failed_delivery(self.reason)
