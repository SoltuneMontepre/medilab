from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.tools import float_compare, format_date

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_CHART_TEMPLATE,
    MODEL_ACCOUNT_TAX,
    MODEL_TAX,
    MODEL_TAX_RATE,
)
from odoo.addons.sol_commerce.constants.pricing import CHART_VAT_EXEMPTION_TAX, NOT_SUBJECT_TAX_CODE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_tax_rate as TaxRateBase
else:
    TaxRateBase = object


# Thuế Suất
class TaxRate(models.Model, TaxRateBase):
    _name = MODEL_TAX_RATE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Tax Rate"
    _order = "tax_id, valid_from"

    if not TYPE_CHECKING:
        # The tax.
        tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="cascade")
        # Rate in percent, such as 8 or 10; 0 for a tax that adds nothing.
        rate = fields.Float(string="Rate (%)", required=True, digits=0)
        # First day the rate applies.
        valid_from = fields.Date(required=True)
        # Last day the rate applies; empty when it applies until further notice.
        valid_until = fields.Date()
        # The accounting sales tax that quotation and invoice lines get for this rate; empty for the company's sales
        # tax of the same rate.
        account_tax_id = fields.Many2one(
            MODEL_ACCOUNT_TAX,
            string="Accounting Tax",
            ondelete="restrict",
            domain="[('type_tax_use', '=', 'sale'), ('amount_type', '=', 'percent'), ('amount', '=', rate)]",
        )

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

    @api.constrains("rate", "account_tax_id")
    def _check_account_tax(self):
        for rate in self.filtered("account_tax_id"):
            tax = rate.account_tax_id.sudo()
            if (
                tax.type_tax_use != "sale"
                or tax.amount_type != "percent"
                or float_compare(tax.amount, rate.rate, precision_digits=4)
            ):
                raise ValidationError(
                    self.env._(
                        "The accounting tax of %(rate)s must be a sales tax of %(percent)s%%.",
                        rate=rate.display_name,
                        percent=f"{rate.rate:g}",
                    )
                )

    def _account_tax(self, company):
        """Return the company's sales tax that lines get for this rate: the one chosen on the rate, otherwise the
        default one of its percent.

        While modules install, the company may not have its chart of accounts yet, so no tax is returned; otherwise a
        rate without a sales tax is refused.
        """
        self.ensure_one()
        if self.account_tax_id:
            tax = self.account_tax_id.sudo()._filter_taxes_by_company(company)
        else:
            tax = self._default_account_tax(company)
        if not tax and self.env.registry.ready:
            raise UserError(
                self.env._(
                    "Accounting has no sales tax for %(rate)s in %(company)s. Choose one on the rate.",
                    rate=self.display_name,
                    company=company.display_name,
                )
            )
        return tax.sudo(False)

    def _default_account_tax(self, company):
        """The chart's VAT exemption for the tax not subject to VAT, which invoices print differently from 0% VAT;
        otherwise the company's first sales tax of the rate that is excluded from the price."""
        if self.tax_id.code == NOT_SUBJECT_TAX_CODE and not self.rate:
            exemption = (
                self.env[MODEL_ACCOUNT_CHART_TEMPLATE]
                .sudo()
                .with_company(company)
                .ref(CHART_VAT_EXEMPTION_TAX, raise_if_not_found=False)
            )
            if exemption and exemption.active:
                return exemption
        taxes = self.env[MODEL_ACCOUNT_TAX].sudo().with_company(company)
        return taxes.search(
            Domain(taxes._check_company_domain(company))
            & Domain("type_tax_use", "=", "sale")
            & Domain("amount_type", "=", "percent")
            & Domain("amount", "=", self.rate),
            order="sequence, id",
        ).filtered(lambda candidate: not candidate.price_include)[:1]
