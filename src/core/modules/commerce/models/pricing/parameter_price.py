from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.commerce.constants.models import (
    MODEL_PARAMETER_PRICE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_TAX,
    MODEL_VND_MIXIN,
)
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_TEST_PARAMETER


# Giá Chỉ Tiêu
class ParameterPrice(models.Model):
    _name = MODEL_PARAMETER_PRICE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN]
    _description = "Parameter Price"
    _order = "parameter_id"
    _rec_name = "parameter_id"

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
            lambda line: (
                self.currency_id.compare_amounts(
                    line.package_id.list_price, line.package_id.parts_price + line.quantity * change
                )
                > 0
            )
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
