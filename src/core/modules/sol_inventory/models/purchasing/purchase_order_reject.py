from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_PURCHASE_ORDER_REJECT


# Từ Chối Đơn Mua Hàng
class PurchaseOrderReject(models.TransientModel):
    _name = MODEL_PURCHASE_ORDER_REJECT
    _description = "Reject a Purchase Order"

    # The purchase order whose approval is rejected.
    order_id = fields.Many2one(MODEL_PURCHASE_ORDER, required=True, ondelete="cascade")
    # Why the approval is rejected; the person who asked for it receives it.
    reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.order_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
