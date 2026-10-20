from odoo import api, models

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_PURCHASE_ORDER_LINE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

# What the signers approved on a line; Odoo keeps writing the others, such as the received quantity.
SIGNED_LINE_FIELDS = frozenset({"product_id", "product_qty", "uom_id", "price_unit", "discount", "tax_ids", "name"})


# Dòng Đơn Mua Hàng
class PurchaseOrderLine(models.Model):
    _name = MODEL_PURCHASE_ORDER_LINE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PURCHASE_ORDER_LINE]

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals["order_id"] for vals in vals_list if vals.get("order_id")]
        self.env[MODEL_PURCHASE_ORDER].browse(order_ids)._check_unsigned()
        return super().create(vals_list)

    def write(self, vals):
        if SIGNED_LINE_FIELDS & set(vals):
            self.order_id._check_unsigned()
        return super().write(vals)

    def unlink(self):
        self.order_id._check_unsigned()
        return super().unlink()
