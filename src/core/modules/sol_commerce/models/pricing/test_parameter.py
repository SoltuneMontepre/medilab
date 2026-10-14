from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER


# Chỉ Tiêu
class TestParameter(models.Model):
    _inherit = MODEL_TEST_PARAMETER
    _audit_children = ("method_ids", "price_ids")

    # The parameter's catalog price; at most one.
    price_ids = fields.One2many(MODEL_PARAMETER_PRICE, "parameter_id", string="Price")

    def write(self, vals):
        if vals.get("active") is False:
            products = self.price_ids._catalog_products()
            products._refuse_if_on_open_orders()
            products.write({"sale_ok": False})
        result = super().write(vals)
        if {"name", "active"} & set(vals):
            self.price_ids._sync_catalog_product()
        return result
