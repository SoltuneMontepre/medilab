from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_date

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PARAMETER_PRICE,
    MODEL_PRICE_PERIOD,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SERVICE_PACKAGE,
    MODEL_TAX,
    MODEL_VND_MIXIN,
)
from odoo.addons.sol_commerce.constants.pricing import PRICE_REFRESH
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
    _audit_children = ("period_ids",)

    if not TYPE_CHECKING:
        # The parameter the price is for.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="cascade")
        # Price of one test in force today, excluding VAT; 0 when no period covers today. Writing it sets that price
        # from today.
        list_price = fields.Monetary(string="Price Today", default=0)
        # The price of one test over time.
        period_ids = fields.One2many(MODEL_PRICE_PERIOD, "parameter_price_id", string="Price Periods")
        # The tax added to the price on quotations and invoices.
        tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="restrict", index=True)
        # False when the price is archived and the parameter is no longer sold.
        active = fields.Boolean(default=True)

    _parameter_unique = models.Constraint(
        "UNIQUE(parameter_id)", "A test parameter has only one price, archived prices included."
    )
    _price_positive = models.Constraint("CHECK(list_price >= 0)", "A price cannot be negative.")

    @api.model_create_multi
    def create(self, vals_list):
        # A price given without periods applies from today until further notice; one given with periods starts as the
        # price of the period covering today, so creating it records no change of that price.
        today = fields.Date.context_today(self)
        prices = []
        for vals in vals_list:
            if vals.get("period_ids"):
                prices.append(None)
                vals["list_price"] = self._price_in_commands(vals["period_ids"], today)
            else:
                prices.append(vals.get("list_price"))
        records = super().create(vals_list)
        for record, price in zip(records, prices, strict=True):
            if price is not None:
                record._set_price_from(today, price)
        records._sync_catalog_product()
        return records

    def write(self, vals):
        if vals.get("active") is False:
            products = self._catalog_products()
            products._refuse_if_on_open_orders()
            products.write({"sale_ok": False})
        new_price = None
        if "list_price" in vals and not self.env.context.get(PRICE_REFRESH):
            vals = dict(vals)
            new_price = vals.pop("list_price")
        result = super().write(vals) if vals else True
        if new_price is not None:
            self._set_price_from(fields.Date.context_today(self), new_price)
        self._sync_catalog_product()
        return result

    @api.model
    def _price_in_commands(self, commands, date):
        """The price of the period that commands create covering the date; 0 when none does."""
        for command in commands:
            if command[0] != Command.CREATE:
                continue
            period = command[2]
            start = fields.Date.to_date(period.get("valid_from")) or date
            end = fields.Date.to_date(period.get("valid_until"))
            if start <= date and (not end or end >= date):
                return period.get("list_price", 0)
        return 0

    def _period_on(self, date):
        """Return the period in force on the date; empty when none covers it."""
        self.ensure_one()
        return self.env[MODEL_PRICE_PERIOD].search(
            Domain("parameter_price_id", "=", self.id)
            & Domain("valid_from", "<=", date)
            & (Domain("valid_until", "=", False) | Domain("valid_until", ">=", date)),
            limit=1,
        )

    def _price_on(self, date):
        """Return the price of one test in force on the date; refuse when no period covers it."""
        period = self._period_on(date) if self else self.env[MODEL_PRICE_PERIOD]
        if not period:
            raise UserError(
                self.env._(
                    "%(parameter)s has no price on %(date)s.",
                    parameter=self.parameter_id.display_name or "",
                    date=format_date(self.env, date),
                )
            )
        return period.list_price

    def _is_priced_on(self, date):
        return bool(self) and self.active and bool(self._period_on(date))

    def _set_price_from(self, date, price):
        """Make the price apply from the date: a period starting that day takes the price, otherwise the period in
        force ends the day before and a new one takes over until the old one would have ended."""
        periods = self.env[MODEL_PRICE_PERIOD].with_context(**{PRICE_REFRESH: True})
        for record in self.with_context(**{PRICE_REFRESH: True}):
            current = record._period_on(date)
            if current and current.valid_from == date:
                current.list_price = price
                continue
            if current:
                until = current.valid_until
                current.valid_until = date - timedelta(days=1)
            else:
                later = periods.search(
                    Domain("parameter_price_id", "=", record.id) & Domain("valid_from", ">", date),
                    order="valid_from",
                    limit=1,
                )
                until = later.valid_from - timedelta(days=1) if later.valid_from else False
            periods.create(
                {"parameter_price_id": record.id, "list_price": price, "valid_from": date, "valid_until": until}
            )
        self._refresh_list_price()

    def _refresh_list_price(self):
        """Bring the price today in line with the periods, and the catalog products with it."""
        today = fields.Date.context_today(self)
        for record in self:
            price = record._period_on(today).list_price
            if record.currency_id.compare_amounts(record.list_price, price):
                record.with_context(**{PRICE_REFRESH: True}).write({"list_price": price})
            else:
                record._sync_catalog_product()

    def _catalog_products(self):
        return self.env[MODEL_PRODUCT_TEMPLATE].sudo().search([("parameter_id", "in", self.parameter_id.ids)])

    def _sync_catalog_product(self):
        """Keep the parameters' products, and the products of the packages that contain them, aligned."""
        products = self.env[MODEL_PRODUCT_TEMPLATE]
        for price in self:
            products._sync_parameter_product(price)
        packages = (
            self.env[MODEL_SERVICE_PACKAGE].sudo().search([("line_ids.parameter_id", "in", self.parameter_id.ids)])
        )
        packages._sync_catalog_product()
