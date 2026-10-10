from odoo import fields, models

from odoo.addons.commerce.constants.models import MODEL_PARAMETER_PRICE
from odoo.addons.laboratory.constants.models import MODEL_TEST_PARAMETER


# Chỉ Tiêu
class TestParameter(models.Model):
    _inherit = MODEL_TEST_PARAMETER

    # The parameter's catalog price; at most one.
    price_ids = fields.One2many(MODEL_PARAMETER_PRICE, "parameter_id", string="Price")
