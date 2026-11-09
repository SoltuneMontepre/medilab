from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_DISCOUNT
from odoo.addons.sol_commerce.constants.xml_ids import DISCOUNT_PRODUCT

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_discount as SaleOrderDiscountBase
else:
    SaleOrderDiscountBase = object


# Chiết Khấu Báo Giá: the discount Sales gives every line or the whole quotation, always a percentage.
class SaleOrderDiscount(models.TransientModel, SaleOrderDiscountBase):
    _inherit = MODEL_SALE_ORDER_DISCOUNT

    if not TYPE_CHECKING:
        # Whether the percentage goes on every line or on one discount line for the whole quotation; a fixed amount
        # is not offered.
        discount_type = fields.Selection(
            selection="_selection_discount_type",
            default="sol_discount",
        )

    @api.model
    def _selection_discount_type(self):
        every_line = self.env._("On every line")
        whole_quotation = self.env._("On the whole quotation")
        return [("sol_discount", every_line), ("so_discount", whole_quotation)]

    def _get_discountable_order_lines(self):
        """Only the ordered parameters and packages: never a down payment or an earlier discount line."""
        return self.sale_order_id._catalog_lines()

    def _get_discount_product(self):
        """The module's discount service, so Sales never needs to create a product or change the company."""
        return self.env.ref(DISCOUNT_PRODUCT)
