from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLinePriorityBase
else:
    SaleOrderLinePriorityBase = object

# Line fields whose change moves the standard return date or the surcharge.
PRIORITY_LINE_FIELDS = frozenset(
    {"product_id", "product_uom_qty", "price_unit", "discount", "tax_ids", "parameter_method_id", "sample_type_id"}
)


# Dòng Đơn Hàng: a changed line brings its order's priority request and surcharge in line.
class SaleOrderLinePriority(models.Model, SaleOrderLinePriorityBase):
    _inherit = MODEL_SALE_ORDER_LINE

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._sync_priority()
        return lines

    def write(self, vals):
        result = super().write(vals)
        if PRIORITY_LINE_FIELDS & set(vals):
            self.order_id._sync_priority()
        return result

    def unlink(self):
        orders = self.order_id
        result = super().unlink()
        orders._sync_priority()
        return result
