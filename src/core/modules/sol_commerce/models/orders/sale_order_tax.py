from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderTaxBase
else:
    SaleOrderTaxBase = object


# Đơn Hàng: a new quotation date gives the lines not yet quoted the tax rate in force on it.
class SaleOrderTax(models.Model, SaleOrderTaxBase):
    _inherit = MODEL_SALE_ORDER

    def write(self, vals):
        result = super().write(vals)
        if "date_order" in vals:
            self.order_line._refresh_catalog_taxes()
        return result
