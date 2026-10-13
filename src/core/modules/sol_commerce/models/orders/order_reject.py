from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_REJECT, MODEL_SALE_ORDER


# Từ Chối Đơn Hàng
class OrderReject(models.TransientModel):
    _name = MODEL_ORDER_REJECT
    _description = "Reject an Order"

    # The order whose approval is rejected.
    order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
    # Why the approval is rejected; the salesperson receives it.
    reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.order_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
