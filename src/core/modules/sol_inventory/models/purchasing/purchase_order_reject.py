from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_PURCHASE_ORDER_REJECT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_purchase_order_reject as PurchaseOrderRejectBase
else:
    PurchaseOrderRejectBase = object


# Từ Chối Đơn Mua Hàng
class PurchaseOrderReject(models.TransientModel, PurchaseOrderRejectBase):
    _name = MODEL_PURCHASE_ORDER_REJECT
    _description = "Reject a Purchase Order"

    if not TYPE_CHECKING:
        # The purchase order whose approval is rejected.
        order_id = fields.Many2one(MODEL_PURCHASE_ORDER, required=True, ondelete="cascade")
        # Why the approval is rejected; the person who asked for it receives it.
        reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.order_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
