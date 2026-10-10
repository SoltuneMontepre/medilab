from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import format_date

from odoo.addons.commerce.constants.models import MODEL_TAX, MODEL_TAX_RATE
from odoo.addons.laboratory.constants.models import MODEL_PERMISSION_MIXIN


# Thuế Suất
class TaxRate(models.Model):
    _name = MODEL_TAX_RATE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Tax Rate"
    _order = "tax_id, valid_from"

    # The tax.
    tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="cascade")
    # Rate in percent, such as 8 or 10; 0 for a tax that adds nothing.
    rate = fields.Float(string="Rate (%)", required=True, digits=0)
    # First day the rate applies.
    valid_from = fields.Date(required=True)
    # Last day the rate applies; empty when it applies until further notice.
    valid_until = fields.Date()

    _tax_valid_from_index = models.Index("(tax_id, valid_from)")
    _rate_positive = models.Constraint("CHECK(rate >= 0)", "A tax rate cannot be negative.")
    _period_order = models.Constraint(
        "CHECK(valid_until IS NULL OR valid_until >= valid_from)",
        "A rate period cannot end before it starts.",
    )

    @api.depends("tax_id", "rate", "valid_from", "valid_until")
    def _compute_display_name(self):
        for rate in self:
            period = f"{format_date(self.env, rate.valid_from)} – {format_date(self.env, rate.valid_until) or '…'}"
            rate.display_name = f"{rate.tax_id.code} {rate.rate:g}% ({period})"

    @api.constrains("tax_id", "valid_from", "valid_until")
    def _check_no_overlap(self):
        for rate in self:
            domain = (
                Domain("tax_id", "=", rate.tax_id.id)
                & Domain("id", "!=", rate.id)
                & (Domain("valid_until", "=", False) | Domain("valid_until", ">=", rate.valid_from))
            )
            if rate.valid_until:
                domain &= Domain("valid_from", "<=", rate.valid_until)
            overlapping = self.search(domain, limit=1)
            if overlapping:
                raise ValidationError(
                    self.env._(
                        "The rate periods of %(tax)s overlap: %(rate)s and %(other)s.",
                        tax=rate.tax_id.display_name,
                        rate=rate.display_name,
                        other=overlapping.display_name,
                    )
                )
