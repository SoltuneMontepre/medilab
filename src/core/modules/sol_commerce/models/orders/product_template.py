from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SALE_ORDER_LINE,
    MODEL_SERVICE_PACKAGE,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PARAMETER_GROUP,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_product_template as ProductTemplateBase
else:
    ProductTemplateBase = object


# Sản Phẩm
class ProductTemplate(models.Model, ProductTemplateBase):
    _name = MODEL_PRODUCT_TEMPLATE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PRODUCT_TEMPLATE]

    if not TYPE_CHECKING:
        # The parameter this product sells; empty for a package.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, ondelete="restrict", index=True)
        # The service package this product sells; empty for a parameter.
        service_package_id = fields.Many2one(MODEL_SERVICE_PACKAGE, ondelete="restrict", index=True)
        # The sample types every parameter the product sells can be ordered on.
        orderable_sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE,
            string="Orderable Sample Types",
            compute="_compute_orderable_sample_type_ids",
            search="_search_orderable_sample_type_ids",
        )

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

    def _sold_parameters(self):
        """The parameter a parameter product sells, or the parameters a package product includes; none without a
        product."""
        if not self:
            return self.env[MODEL_TEST_PARAMETER]
        self.ensure_one()
        template = self.sudo()
        return template.parameter_id or template.service_package_id.line_ids.parameter_id

    def _orderable_sample_types(self, partner=None):
        """The sample types every parameter the product sells can be ordered on, with a way of testing offered to the
        partner."""
        parameters = self._sold_parameters()
        if not parameters:
            return self.env[MODEL_SAMPLE_TYPE]
        candidates = parameters[0].sample_type_ids
        for parameter in parameters[1:]:
            candidates &= parameter.sample_type_ids
        return candidates.filtered(
            lambda sample_type: (
                not any(
                    parameter._order_refusal(sample_type) or not parameter._offered_ways(sample_type, partner)
                    for parameter in parameters
                )
            )
        ).sorted("name")

    @api.depends("parameter_id.sample_type_ids", "service_package_id.line_ids.parameter_id.sample_type_ids")
    def _compute_orderable_sample_type_ids(self):
        for template in self:
            template.orderable_sample_type_ids = template._orderable_sample_types()

    def _search_orderable_sample_type_ids(self, operator, value):
        if operator != "in":
            return NotImplemented
        wanted = self.env[MODEL_SAMPLE_TYPE].browse(value)
        candidates = (
            self.with_context(active_test=False)
            .sudo()
            .search(
                Domain("parameter_id.sample_type_ids", "in", wanted.ids)
                | Domain("service_package_id.line_ids.parameter_id.sample_type_ids", "in", wanted.ids)
            )
        )
        orderable = candidates.filtered(lambda template: bool(template._orderable_sample_types() & wanted))
        return Domain("id", "in", orderable.ids)

    @api.model
    def _orderable_sample_types_of_catalog(self):
        """The sample types at least one parameter on sale can be ordered on."""
        parameters = self.sudo().search(self._catalog_domain()).parameter_id
        return parameters.sample_type_ids.sorted("name")

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
        names = [name or "" for name in lines.order_id.mapped("display_name")]
        raise UserError(self.env._("This cannot be archived while these orders use it:\n%s", "\n".join(names)))

    def _sync_parameter_product(self, price):
        """Keep the parameter's product aligned with its catalog price."""
        self._sync_catalog_product(
            price.parameter_id,
            "parameter_id",
            price.parameter_id.name,
            price.list_price,
            price.parameter_id.active and price._is_priced_on(fields.Date.context_today(self)),
        )

    def _sync_package_product(self, package):
        """Keep the package's product aligned with the package price."""
        offered = package.active and package._is_priced_on(fields.Date.context_today(self))
        self._sync_catalog_product(package, "service_package_id", package.name, package.list_price, offered)

    def _sync_catalog_product(self, owner, field_name, name, list_price, offered):
        product = self.sudo().search([(field_name, "=", owner.id)], limit=1)
        vals = {"name": name, "list_price": list_price, "sale_ok": bool(offered), field_name: owner.id}
        if product:
            current = product.read(list(vals), load="")[0]
            changed = {key: value for key, value in vals.items() if current[key] != value}
            product._copy_name_translations(owner)
            if not changed:
                return product
            product.write(changed)
        else:
            product = self.sudo().create(
                {**vals, "type": "service", "purchase_ok": False, "taxes_id": [Command.clear()]}
            )
            product._copy_name_translations(owner)
        product._refresh_draft_cart_prices()
        return product

    def _copy_name_translations(self, owner):
        """Give the product the name of its parameter or package in every installed language, so the cart and
        quotations show it in the customer's language."""
        for code, _name in self.env["res.lang"].get_installed():
            name = owner.with_context(lang=code).name
            if self.with_context(lang=code).name != name:
                self.with_context(lang=code).name = name

    def _refresh_draft_cart_prices(self):
        lines = (
            self.env[MODEL_SALE_ORDER_LINE]
            .sudo()
            .search(
                Domain("product_id.product_tmpl_id", "in", self.ids)
                & Domain("order_id.order_status", "=", "draft")
                & Domain("display_type", "=", False)
            )
        )
        lines._lock_catalog_price(skip_unpriced=True)

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

    def _catalog_offer(self):
        """What the catalog shows of the product: its name and today's price, the day the price next changes and the
        price from then, and for a package its parameters; for a parameter its sample types."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        package = self.service_package_id
        prices = (package.line_ids.parameter_id if package else self.parameter_id).price_ids
        upcoming = prices.period_ids.filtered(
            lambda period: bool(period.valid_from and period.valid_from > today)
        ).sorted("valid_from")[:1]
        priced = package or self.parameter_id.price_ids[:1]
        if upcoming and not priced._is_priced_on(upcoming.valid_from):
            upcoming = upcoming.browse()
        return {
            "name": (package or self.parameter_id).name,
            "price": priced.list_price,
            "next_date": upcoming.valid_from,
            "next_price": priced._price_on(upcoming.valid_from) if upcoming else 0,
            "lines": package.line_ids,
            "sample_types": ", ".join(name or "" for name in self.parameter_id.sample_type_ids.mapped("name")),
        }

    def _package_extras(self):
        """The parameter products on sale that a customer can add to the package, by name."""
        self.ensure_one()
        return self.sudo().search(
            Domain("sale_ok", "=", True)
            & Domain("parameter_id", "!=", False)
            & Domain("parameter_id", "not in", self.service_package_id.line_ids.parameter_id.ids),
            order="name",
        )

    @api.model
    def catalog_filters(self):
        return {
            "sample_types": self.env[MODEL_SAMPLE_TYPE].sudo().search(Domain.TRUE),
            "groups": self.env[MODEL_PARAMETER_GROUP].sudo().search(Domain.TRUE),
        }
