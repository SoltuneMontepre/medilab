from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderTaxBase
else:
    SaleOrderTaxBase = object


# Đơn Hàng: the lines not yet quoted take the tax rate in force on the quotation date.
class SaleOrderTax(models.Model, SaleOrderTaxBase):
    _inherit = MODEL_SALE_ORDER

    def write(self, vals):
        result = super().write(vals)
        if "date_order" in vals:
            self.order_line._refresh_catalog_taxes()
        return result

    def action_send_quotation(self):
        # A cart line whose tax had no rate when the customer added it gets its tax before the quotation is sent.
        self._catalog_lines().filtered(lambda line: not line.tax_ids)._refresh_catalog_taxes()
        return super().action_send_quotation()
