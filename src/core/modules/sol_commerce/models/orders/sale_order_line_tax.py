import logging
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_TAX, MODEL_SALE_ORDER_LINE
from odoo.addons.sol_commerce.constants.orders import STATUS_CLAIMED, STATUS_DRAFT, STATUS_SUBMITTED

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLineTaxBase
else:
    SaleOrderLineTaxBase = object

_logger = logging.getLogger(__name__)


# Dòng Đơn Hàng: a catalog line takes the tax of its parameter or package at the rate in force on the quotation date.
class SaleOrderLineTax(models.Model, SaleOrderLineTaxBase):
    _inherit = MODEL_SALE_ORDER_LINE

    def _compute_tax_ids(self):
        open_lines = self - self._frozen_lines()
        catalog = open_lines.filtered(lambda line: not line.display_type and bool(line._catalog_tax()))
        result = super(SaleOrderLineTax, open_lines - catalog)._compute_tax_ids()
        # Odoo gives a line without a product the company's default tax; a MediLab line takes the tax of its parameter
        # or package.
        for line in (open_lines - catalog).filtered(lambda line: not line.product_id):
            line.tax_ids = False
        catalog._set_catalog_taxes()
        return result

    def _refresh_catalog_taxes(self):
        """Give the catalog lines whose quotation was not sent the tax in force on their order's quotation date."""
        (self._catalog_lines() - self._frozen_lines())._set_catalog_taxes()

    def _set_catalog_taxes(self):
        """Give each line the account tax of its catalog tax, looking each tax, date and fiscal position up once.

        A customer's cart shows no tax, so a tax without a rate on the date leaves the cart line untaxed instead of
        refusing the customer; sending the quotation gives it its tax or tells sales what is missing.
        """
        found = {}
        for line in self:
            key = line._catalog_tax_key()
            if key not in found:
                try:
                    found[key] = line._catalog_account_tax()
                except UserError:
                    if not self.env.user.share:
                        raise
                    found[key] = self.env[MODEL_ACCOUNT_TAX]
            line.tax_ids = found[key]

    def _catalog_tax_key(self):
        order = self.order_id
        return (self._catalog_tax(), self._quotation_date(), self._tax_company(), order.fiscal_position_id)

    def _catalog_tax(self):
        """The tax of the line's parameter price or package; empty for a line outside the catalog."""
        self.ensure_one()
        template = self.product_id.product_tmpl_id.sudo()
        if template.service_package_id:
            return template.service_package_id.tax_id
        return template.parameter_id.with_context(active_test=False).price_ids[:1].tax_id

    def _catalog_account_tax(self):
        """The company's sales tax for the line's tax at the rate in force on the quotation date, mapped by the
        order's fiscal position."""
        self.ensure_one()
        company = self._tax_company()
        tax = self._catalog_tax()._account_tax_on(self._quotation_date(), company)
        return self.order_id.fiscal_position_id.map_tax(tax.with_company(company))

    def _tax_company(self):
        return self.company_id or self.order_id.company_id or self.env.company

    def _quotation_date(self):
        """The order's quotation date in the user's time zone; today for an order still being created."""
        moment = self.order_id.date_order
        return fields.Date.context_today(self, moment) if moment else fields.Date.context_today(self)

    @api.model
    def _tax_untaxed_drafts(self):
        """Give the catalog lines without a tax of orders not yet quoted, confirmed or invoiced the tax of their
        parameter or package; the other orders keep the taxes they were quoted with."""
        lines = (
            self.sudo()
            .search(
                Domain("order_id.state", "=", "draft")
                & Domain("order_id.quotation_ids", "=", False)
                & Domain("order_id.order_status", "in", (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_CLAIMED))
                & Domain("order_id.invoice_ids", "=", False)
                & Domain("display_type", "=", False)
                & Domain("linked_line_id", "=", False)
                & Domain("tax_ids", "=", False)
            )
            ._catalog_lines()
        )
        for order, order_lines in lines.grouped("order_id").items():
            try:
                with self.env.cr.savepoint():
                    order_lines._set_catalog_taxes()
                    order_lines.flush_recordset()
            except UserError as error:
                _logger.warning("%s keeps lines without tax: %s", order.name, error)
