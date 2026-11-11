from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PARAMETER_PRICE,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_TAX,
    MODEL_VND_MIXIN,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN, MODEL_TEST_PARAMETER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_parameter_price as ParameterPriceBase
else:
    ParameterPriceBase = object


# Giá Chỉ Tiêu
class ParameterPrice(models.Model, ParameterPriceBase):
    _name = MODEL_PARAMETER_PRICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Parameter Price"
    _order = "parameter_id"
    _rec_name = "parameter_id"

    if not TYPE_CHECKING:
        # The parameter the price is for.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="cascade")
        # Price of one test, excluding VAT.
        list_price = fields.Monetary(string="Price", required=True)
        # The tax added to the price on quotations and invoices.
        tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="restrict", index=True)
        # False when the price is archived and the parameter is no longer sold.
        active = fields.Boolean(default=True)

    _parameter_unique = models.Constraint(
        "UNIQUE(parameter_id)", "A test parameter has only one price, archived prices included."
    )
    _price_positive = models.Constraint("CHECK(list_price >= 0)", "A price cannot be negative.")

    @api.onchange("list_price")
    def _onchange_list_price(self):
        # Warns whoever lowers the price about the active packages it makes cost more than their parts.
        change = self.list_price - self._origin.list_price
        if change >= 0:
            return None
        lines = self.env[MODEL_SERVICE_PACKAGE_LINE].search(
            Domain("parameter_id", "=", self.parameter_id._origin.id) & Domain("package_id.active", "=", True)
        )
        packages = lines.filtered(
            lambda line: line.package_id._costs_more_than_parts(line.quantity * change)
        ).package_id
        if not packages:
            return None
        return {
            "warning": {
                "title": self.env._("Package prices"),
                "message": self.env._(
                    "With this price, these packages cost more than their parameters bought one by one: %s",
                    format_list(self.env, packages.mapped("display_name")),
                ),
            }
        }

    @api.model_create_multi
    def create(self, vals_list):
        prices = super().create(vals_list)
        prices._sync_catalog_product()
        return prices

    def write(self, vals):
        if vals.get("active") is False:
            products = self._catalog_products()
            products._refuse_if_on_open_orders()
            products.write({"sale_ok": False})
        result = super().write(vals)
        self._sync_catalog_product()
        return result

    def _catalog_products(self):
        return self.env[MODEL_PRODUCT_TEMPLATE].sudo().search([("parameter_id", "in", self.parameter_id.ids)])

    def _sync_catalog_product(self):
        products = self.env[MODEL_PRODUCT_TEMPLATE]
        for price in self:
            products._sync_parameter_product(price)
