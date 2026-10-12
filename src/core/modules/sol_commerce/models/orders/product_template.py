from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SALE_ORDER_LINE,
    MODEL_SERVICE_PACKAGE,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_GROUP, MODEL_SAMPLE_TYPE, MODEL_TEST_PARAMETER


# Sản Phẩm
class ProductTemplate(models.Model):
    _name = MODEL_PRODUCT_TEMPLATE
    _inherit = MODEL_PRODUCT_TEMPLATE

    # The parameter this product sells; empty for a package.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, ondelete="restrict", index=True)
    # The service package this product sells; empty for a parameter.
    service_package_id = fields.Many2one(MODEL_SERVICE_PACKAGE, ondelete="restrict", index=True)

    _catalog_kind = models.Constraint(
        "CHECK(parameter_id IS NULL OR service_package_id IS NULL)",
        "A product sells a parameter or a package, not both.",
    )
    _parameter_unique = models.Constraint(
        "UNIQUE(parameter_id)", "A test parameter has only one product, archived products included."
    )
    _package_unique = models.Constraint(
        "UNIQUE(service_package_id)", "A service package has only one product, archived products included."
    )

    def _in_use_domain(self):
        # Selling the product is what keeps the parameter or package from being archived.
        return Domain("sale_ok", "=", True)

    def _open_order_lines(self):
        return (
            self.env[MODEL_SALE_ORDER_LINE]
            .sudo()
            .search(
                Domain("product_id.product_tmpl_id", "in", self.ids)
                & Domain("order_id.order_status", "not in", ("cancelled", "completed"))
                & Domain("display_type", "=", False)
            )
        )

    def _refuse_if_on_open_orders(self):
        lines = self._open_order_lines()
        if not lines:
            return
        names = lines.order_id.mapped("display_name")
        raise UserError(self.env._("This cannot be archived while these orders use it:\n%s", "\n".join(names)))

    def _sync_parameter_product(self, price):
        """Keep the parameter's product aligned with its catalog price."""
        self._sync_catalog_product(
            price.parameter_id,
            "parameter_id",
            price.parameter_id.name,
            price.list_price,
            price.active and price.parameter_id.active,
        )

    def _sync_package_product(self, package):
        """Keep the package's product aligned with the package price."""
        self._sync_catalog_product(package, "service_package_id", package.name, package.list_price, package.active)

    def _sync_catalog_product(self, owner, field_name, name, list_price, offered):
        product = self.sudo().search([(field_name, "=", owner.id)], limit=1)
        vals = {"name": name, "list_price": list_price, "sale_ok": bool(offered), field_name: owner.id}
        if product:
            product.write(vals)
            return product
        return self.sudo().create({**vals, "type": "service", "purchase_ok": False, "taxes_id": [Command.clear()]})

    @api.model
    def _catalog_domain(self, sample_type=None, group=None, name=None, price_min=None, price_max=None):
        domain = Domain("sale_ok", "=", True) & (
            Domain("parameter_id", "!=", False) | Domain("service_package_id", "!=", False)
        )
        if name:
            domain &= Domain("name", "ilike", name)
        if price_min not in (None, ""):
            domain &= Domain("list_price", ">=", float(price_min))
        if price_max not in (None, ""):
            domain &= Domain("list_price", "<=", float(price_max))
        if sample_type:
            domain &= Domain("parameter_id.sample_type_ids", "child_of", sample_type.id) | Domain(
                "service_package_id.line_ids.parameter_id.sample_type_ids", "child_of", sample_type.id
            )
        if group:
            domain &= Domain("parameter_id.group_ids", "child_of", group.id) | Domain(
                "service_package_id.line_ids.parameter_id.group_ids", "child_of", group.id
            )
        return domain

    @api.model
    @api.model
    def catalog_filters(self):
        return {
            "sample_types": self.env[MODEL_SAMPLE_TYPE].sudo().search([]),
            "groups": self.env[MODEL_PARAMETER_GROUP].sudo().search([]),
        }
