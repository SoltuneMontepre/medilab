from odoo import api, fields, models

from odoo.addons.commerce.constants.models import (
    MODEL_PARAMETER_PRICE,
    MODEL_SERVICE_PACKAGE,
    MODEL_SERVICE_PACKAGE_LINE,
)
from odoo.addons.laboratory.constants.models import MODEL_TEST_PARAMETER


# Chỉ Tiêu
class TestParameter(models.Model):
    _inherit = MODEL_TEST_PARAMETER

    # The parameter's catalog price; at most one.
    price_ids = fields.One2many(MODEL_PARAMETER_PRICE, "parameter_id", string="Price")
    # Package lines that include the parameter.
    package_line_ids = fields.One2many(MODEL_SERVICE_PACKAGE_LINE, "parameter_id", string="Package Lines")
    # Active packages that include the parameter and cost more than their parts.
    overpriced_package_ids = fields.Many2many(
        MODEL_SERVICE_PACKAGE, compute="_compute_overpriced_package_ids", string="Overpriced Packages"
    )

    @api.depends("price_ids.list_price", "package_line_ids")
    def _compute_overpriced_package_ids(self):
        for parameter in self:
            parameter.overpriced_package_ids = parameter.package_line_ids.package_id.filtered(
                lambda package: package.active and package.is_overpriced
            )
