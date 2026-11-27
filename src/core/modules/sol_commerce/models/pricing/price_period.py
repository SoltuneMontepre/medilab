from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_PARAMETER_PRICE, MODEL_PRICE_PERIOD, MODEL_VND_MIXIN
from odoo.addons.sol_commerce.constants.pricing import PRICE_REFRESH
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_price_period as PricePeriodBase
else:
    PricePeriodBase = object


# Giá Theo Kỳ
class PricePeriod(models.Model, PricePeriodBase):
    _name = MODEL_PRICE_PERIOD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Price Period"
    _order = "valid_from desc, id desc"

    if not TYPE_CHECKING:
        # The parameter price the period belongs to.
        parameter_price_id = fields.Many2one(MODEL_PARAMETER_PRICE, required=True, ondelete="cascade")
        # Price of one test during the period, excluding VAT.
        list_price = fields.Monetary(string="Price", required=True)
        # First day the price applies.
        valid_from = fields.Date(required=True, default=fields.Date.context_today)
        # Last day the price applies; empty when it applies until further notice.
        valid_until = fields.Date()
        # True when the period covers today.
        is_current = fields.Boolean(string="In Force", compute="_compute_is_current")

    _parameter_price_index = models.Index("(parameter_price_id, valid_from)")
    _price_positive = models.Constraint("CHECK(list_price >= 0)", "A price cannot be negative.")
    _period_order = models.Constraint(
        "CHECK(valid_until IS NULL OR valid_until >= valid_from)",
        "A price period cannot end before it starts.",
    )

    @api.depends("parameter_price_id", "valid_from", "valid_until")
    def _compute_display_name(self):
        for period in self:
            dates = f"{format_date(self.env, period.valid_from)} – {format_date(self.env, period.valid_until) or '…'}"
            period.display_name = f"{period.parameter_price_id.display_name or ''} ({dates})"

    @api.depends("valid_from", "valid_until")
    def _compute_is_current(self):
        today = fields.Date.context_today(self)
        for period in self:
            period.is_current = period._covers(today)

    @api.constrains("parameter_price_id", "valid_from", "valid_until")
    def _check_no_overlap(self):
        for period in self:
            domain = (
                Domain("parameter_price_id", "=", period.parameter_price_id.id)
                & Domain("id", "!=", period.id)
                & (Domain("valid_until", "=", False) | Domain("valid_until", ">=", period.valid_from))
            )
            if period.valid_until:
                domain &= Domain("valid_from", "<=", period.valid_until)
            overlapping = self.search(domain, limit=1)
            if overlapping:
                raise ValidationError(
                    self.env._(
                        "The price periods of %(parameter)s overlap: %(period)s and %(other)s.",
                        parameter=period.parameter_price_id.display_name,
                        period=period.display_name,
                        other=overlapping.display_name,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        periods = super().create(vals_list)
        periods._refresh_prices(periods.parameter_price_id)
        return periods

    def write(self, vals):
        prices = self.parameter_price_id
        result = super().write(vals)
        self._refresh_prices(prices | self.parameter_price_id)
        return result

    def unlink(self):
        prices = self.parameter_price_id
        result = super().unlink()
        self._refresh_prices(prices.exists())
        return result

    def _refresh_prices(self, prices):
        # A price change that moves several periods refreshes the price once, after the last of them.
        if not self.env.context.get(PRICE_REFRESH):
            prices._refresh_list_price()

    def _covers(self, date):
        self.ensure_one()
        return self.valid_from <= date and (not self.valid_until or self.valid_until >= date)

    @api.model
    def _refresh_current_prices(self):
        """Bring every parameter price in line with the periods in force today, so a period that starts or ends
        changes the catalog on its day."""
        prices = self.env[MODEL_PARAMETER_PRICE].with_context(active_test=False, tz=VIETNAM_ZONE)
        prices.search(Domain.TRUE)._refresh_list_price()
