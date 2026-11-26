from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SERVICE_PACKAGE,
    MODEL_SERVICE_PACKAGE_LINE,
    MODEL_TAX,
    MODEL_VND_MIXIN,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_service_package as ServicePackageBase
else:
    ServicePackageBase = object


# Gói Dịch Vụ
class ServicePackage(models.Model, ServicePackageBase):
    _name = MODEL_SERVICE_PACKAGE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_VND_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Service Package"
    _order = "code"
    _rec_names_search = ("name", "code")
    _audit_children = ("line_ids",)

    if not TYPE_CHECKING:
        # Short unique code of the package.
        code = fields.Char(required=True, copy=False, index="trigram")
        # Package name in each language.
        name = fields.Char(required=True, translate=True, index="trigram")
        # The sum of the parameters' prices in force today times their quantities, excluding VAT.
        list_price = fields.Monetary(string="Price Today", compute="_compute_list_price", store=True)
        # The tax added to the price on quotations and invoices.
        tax_id = fields.Many2one(MODEL_TAX, required=True, ondelete="restrict", index=True)
        # False when the package is archived and no longer offered.
        active = fields.Boolean(default=True)
        # Parameters in the package.
        line_ids = fields.One2many(MODEL_SERVICE_PACKAGE_LINE, "package_id", string="Parameters")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a service package must be unique.")

    @api.depends("line_ids.quantity", "line_ids.parameter_id.price_ids.list_price")
    def _compute_list_price(self):
        for package in self:
            package.list_price = sum(
                line.quantity * line.parameter_id.with_context(active_test=False).price_ids[:1].list_price
                for line in package.line_ids
            )

    @api.model_create_multi
    def create(self, vals_list):
        packages = super().create(vals_list)
        packages._sync_catalog_product()
        return packages

    def write(self, vals):
        if vals.get("active") is False:
            products = self._catalog_products()
            products._refuse_if_on_open_orders()
            products.write({"sale_ok": False})
        result = super().write(vals)
        if not self.env.context.get("medilab_skip_catalog_product"):
            self._sync_catalog_product()
        return result

    def _price_on(self, date, parameters=None):
        """Return the price of the package on the date: its parameters' prices times their quantities. Parameters,
        a mapping of parameter to quantity, replaces the package's own when the customer changed them."""
        self.ensure_one()
        if parameters is None:
            parameters = {line.parameter_id: line.quantity for line in self.line_ids}
        return sum(
            quantity * parameter.with_context(active_test=False).price_ids[:1]._price_on(date)
            for parameter, quantity in parameters.items()
        )

    def _is_priced_on(self, date):
        """Whether every parameter of the package has a price on the date, so the package can be sold."""
        self.ensure_one()
        return bool(self.line_ids) and all(
            line.parameter_id.price_ids[:1]._is_priced_on(date) for line in self.line_ids
        )

    def _catalog_products(self):
        return self.env[MODEL_PRODUCT_TEMPLATE].sudo().search([("service_package_id", "in", self.ids)])

    def _sync_catalog_product(self):
        products = self.env[MODEL_PRODUCT_TEMPLATE]
        for package in self:
            products._sync_package_product(package)
