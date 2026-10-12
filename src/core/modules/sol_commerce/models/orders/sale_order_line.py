from odoo import api, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE
from odoo.addons.sol_commerce.constants.orders import PORTAL_LOCKED_LINE_FIELDS


# Dòng Đơn Hàng
class SaleOrderLine(models.Model):
    _name = MODEL_SALE_ORDER_LINE
    _inherit = MODEL_SALE_ORDER_LINE

    def _is_catalog_line(self):
        template = self.product_id.product_tmpl_id
        return bool(template.parameter_id or template.service_package_id)

    def _catalog_lines(self):
        return self.filtered(lambda line: not line.display_type and line._is_catalog_line())

    @api.constrains("product_uom_qty", "product_id", "display_type")
    def _check_catalog_quantity(self):
        for line in self._catalog_lines():
            if line.product_uom_qty < 1:
                raise ValidationError(self.env._("A catalog line needs a quantity of at least 1."))

    def write(self, vals):
        if PORTAL_LOCKED_LINE_FIELDS & set(vals) and self.env.user.share and not self.env.su:
            raise AccessError(self.env._("You cannot change the price of an order."))
        return super().write(vals)

    def _lock_catalog_price(self):
        for line in self._catalog_lines():
            price = line.product_id.product_tmpl_id.list_price
            # A price that differs from technical_price_unit is kept when the quantity changes.
            line.write({"price_unit": price, "technical_price_unit": 0.0 if price else 1.0})
