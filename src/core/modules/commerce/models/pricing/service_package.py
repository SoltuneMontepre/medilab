from odoo import api, fields, models

from odoo.addons.commerce.constants.models import (
    MODEL_SERVICE_PACKAGE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_TAX,
    MODEL_VND_MIXIN,
)
from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_PERMISSION_MIXIN


# Nhóm Dịch Vụ
class ServicePackage(models.Model):
    _name = MODEL_SERVICE_PACKAGE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_VND_MIXIN]
    _description = "Service Package"
    _order = "code"
    _rec_names_search = ("name", "code")

    # Short unique code of the package.
    code = fields.Char(required=True, copy=False)
    # Package name in each language.
    name = fields.Char(required=True, translate=True, index="trigram")
    # Price of the whole package, excluding VAT.
    list_price = fields.Monetary(string="Price", required=True)
    # The tax added to the price on quotations and invoices.
    tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="restrict", index=True)
    # False when the package is archived and no longer offered.
    active = fields.Boolean(default=True)
    # Parameters in the package.
    line_ids = fields.One2many(MODEL_SERVICE_PACKAGE_LINE, "package_id", string="Parameters")
    # Sum of the parameters' own prices times their quantities; a parameter without a price counts as 0.
    parts_price = fields.Monetary(string="Price of the Parts", compute="_compute_parts_price")
    # True when the package costs more than its parameters bought one by one.
    is_overpriced = fields.Boolean(compute="_compute_parts_price")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a service package must be unique.")
    _price_positive = models.Constraint("CHECK(list_price >= 0)", "A price cannot be negative.")

    @api.depends(
        "list_price",
        "line_ids.quantity",
        "line_ids.parameter_id.price_ids.list_price",
        "line_ids.parameter_id.price_ids.active",
    )
    def _compute_parts_price(self):
        for package in self:
            package.parts_price = sum(
                line.quantity * line.parameter_id.price_ids[:1].list_price for line in package.line_ids
            )
            package.is_overpriced = package.currency_id.compare_amounts(package.list_price, package.parts_price) > 0
