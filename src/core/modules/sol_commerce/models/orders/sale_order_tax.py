from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_TAX

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderTaxBase
else:
    SaleOrderTaxBase = object

ORDER_TAX_FIELDS = {"order_tax_id", "chosen_tax_id"}


# Đơn Hàng: one tax for the whole order, which every line takes at the rate in force on the quotation date.
class SaleOrderTax(models.Model, SaleOrderTaxBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # The tax Sales chose for the order; empty while the order takes the usual tax of its lines.
        chosen_tax_id = fields.Many2one(MODEL_TAX, copy=False, ondelete="restrict")
        # The tax of the whole order: the one Sales chose, or else the tax of the parameters and packages that make up
        # most of the order's untaxed value.
        order_tax_id = fields.Many2one(
            MODEL_TAX,
            string="Tax",
            compute="_compute_order_tax_id",
            inverse="_inverse_order_tax_id",
            store=True,
            readonly=False,
            copy=False,
        )

    @api.depends(
        "chosen_tax_id",
        "order_line.product_id",
        "order_line.product_uom_qty",
        "order_line.price_unit",
        "order_line.discount",
    )
    def _compute_order_tax_id(self):
        for order in self:
            # A sent quotation keeps the tax it was sent with.
            if order.order_tax_id and order in order._frozen_by_quotation():
                order.order_tax_id = order.order_tax_id
                continue
            if order.chosen_tax_id:
                order.order_tax_id = order.chosen_tax_id
                continue
            values = {}
            for line in order._catalog_lines():
                tax = line._own_catalog_tax()
                if tax:
                    value = line.product_uom_qty * line.price_unit * (1 - (line.discount or 0) / 100)
                    values[tax] = values.get(tax, 0) + value
            order.order_tax_id = max(values, key=lambda tax: values[tax]) if values else False

    def _inverse_order_tax_id(self):
        for order in self:
            order.chosen_tax_id = order.order_tax_id

    def write(self, vals):
        if ORDER_TAX_FIELDS & set(vals) and self._frozen_by_quotation():
            raise UserError(self.env._("The tax cannot change after the quotation is sent. Revise the quotation."))
        result = super().write(vals)
        if "date_order" in vals:
            self.order_line._lock_catalog_price()
            self.order_line._refresh_catalog_taxes()
        return result

    def action_send_quotation(self):
        # A cart line whose tax had no rate when the customer added it gets its tax before the quotation is sent.
        self._catalog_lines().filtered(lambda line: not line.tax_ids)._refresh_catalog_taxes()
        return super().action_send_quotation()
