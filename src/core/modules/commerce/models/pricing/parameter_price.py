from odoo import fields, models

from odoo.addons.commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_TAX, MODEL_VND_MIXIN
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

    _parameter_unique = models.Constraint("UNIQUE(parameter_id)", "A test parameter has only one price.")
    _price_positive = models.Constraint("CHECK(list_price >= 0)", "A price cannot be negative.")
