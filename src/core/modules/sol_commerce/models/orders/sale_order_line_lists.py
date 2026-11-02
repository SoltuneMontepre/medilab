from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SALE_ORDER_LINE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderBase
else:
    SaleOrderBase = object


# Đơn Hàng: the order form lists the ordered parameters and packages apart from the down payments.
class SaleOrder(models.Model, SaleOrderBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The ordered parameters and packages: every line but Odoo's down payment section and lines.
        product_line_ids = fields.One2many(
            MODEL_SALE_ORDER_LINE,
            "order_id",
            string="Order Lines",
            domain=[("is_downpayment", "=", False)],
            copy=False,
        )
        # The down payment lines Odoo adds when an advance invoice is created, without their section.
        downpayment_line_ids = fields.One2many(
            MODEL_SALE_ORDER_LINE,
            "order_id",
            string="Advance payments",
            domain=[("is_downpayment", "=", True), ("display_type", "=", False)],
            readonly=True,
            copy=False,
        )

    @api.onchange("product_line_ids")
    def _onchange_product_line_ids(self):
        """Give the edited lines back to Odoo's order lines, which the totals follow while the order is edited."""
        self.order_line = self.product_line_ids | self.order_line.filtered("is_downpayment")
