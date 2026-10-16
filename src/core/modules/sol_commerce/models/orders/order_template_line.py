import math

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain
from odoo.tools import float_compare

from .order_template import CREATING_TEMPLATE_IDS, EDITING_TEMPLATE_IDS
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ORDER_TEMPLATE,
    MODEL_ORDER_TEMPLATE_LINE,
    MODEL_PRODUCT_TEMPLATE,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Dòng Đơn Hàng Mẫu
class OrderTemplateLine(models.Model):
    _name = MODEL_ORDER_TEMPLATE_LINE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Order Template Line"
    _order = "template_id, id"
    _permission_actions = ("read", "create", "edit", "delete")

    # The template this selection belongs to.
    template_id = fields.Many2one(MODEL_ORDER_TEMPLATE, required=True, ondelete="cascade", index=True)
    # The parameter or whole-package product, before resolving its current variant.
    product_id = fields.Many2one(MODEL_PRODUCT_TEMPLATE, required=True, ondelete="restrict")
    # How many units to order, preserving fractional sale-line quantities.
    quantity = fields.Float(required=True, default=1, digits="Product Unit")

    _quantity_minimum = models.Constraint(
        "CHECK(quantity >= 1)", "A template selection needs a quantity of at least 1."
    )

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            self._check_quantity_value(line.quantity)

    @api.model
    def _check_quantity_value(self, quantity):
        precision = self.env["decimal.precision"].precision_get("Product Unit")
        try:
            quantity = float(quantity)
        except (TypeError, ValueError, OverflowError):
            quantity = None
        if (
            quantity is None
            or not math.isfinite(quantity)
            or float_compare(quantity, 1, precision_digits=precision) < 0
        ):
            raise ValidationError(self.env._("A template selection needs a quantity of at least 1."))

    @api.model
    def _check_product_identity(self, product_id):
        product = self.env[MODEL_PRODUCT_TEMPLATE].sudo().with_context(active_test=False).browse(product_id).exists()
        if len(product) != 1 or not (product.parameter_id or product.service_package_id):
            raise ValidationError(self.env._("Choose a parameter or package from the catalog."))

    def _check_parent_selections(self, parents):
        parents.filtered(lambda parent: parent.id not in EDITING_TEMPLATE_IDS.get())._check_has_selections()

    def _serialize_selection_removals(self, parents):
        # Updating the parent makes concurrent removals conflict under Repeatable Read.
        parents.write({"write_date": fields.Datetime.now()})

    @api.model_create_multi
    def create(self, vals_list):
        parents = self.env[MODEL_ORDER_TEMPLATE].browse([vals.get("template_id") for vals in vals_list])
        initial = parents.filtered(lambda parent: parent.id in CREATING_TEMPLATE_IDS.get())
        initial.check_access("read")
        existing = parents - initial
        if existing:
            existing.check_access("write")
            existing._check_permission("edit")
        defaults = self.default_get(["product_id", "quantity"])
        for vals in vals_list:
            self._check_product_identity(vals.get("product_id", defaults.get("product_id")))
            self._check_quantity_value(vals.get("quantity", defaults.get("quantity")))
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        parents = self.template_id
        if vals.get("template_id"):
            parents |= self.env[MODEL_ORDER_TEMPLATE].browse(vals["template_id"])
        parents.check_access("write")
        parents._check_permission("edit")
        if "product_id" in vals:
            self._check_product_identity(vals["product_id"])
        if "quantity" in vals:
            self._check_quantity_value(vals["quantity"])
        if "template_id" not in vals:
            return super().write(vals)
        with self.env.cr.savepoint():
            self._serialize_selection_removals(parents)
            result = super().write(vals)
            self._check_parent_selections(parents)
            return result

    def unlink(self):
        self.check_access("unlink")
        parents = self.template_id
        parents.check_access("write")
        parents._check_permission("edit")
        with self.env.cr.savepoint():
            self._serialize_selection_removals(parents)
            result = super().unlink()
            self._check_parent_selections(parents)
            return result

    def _in_use_domain(self):
        return Domain("template_id.active", "=", True)

    def _unavailability_reason(self):
        self.ensure_one()
        product = self.product_id.sudo().with_context(active_test=False)
        reason = self._product_unavailability(product)
        if reason:
            return reason
        package = product.service_package_id
        if package:
            if not package.active or not package.line_ids:
                return self.env._("The package is archived or has no parameters.")
            products = (
                self.env[MODEL_PRODUCT_TEMPLATE]
                .sudo()
                .with_context(active_test=False)
                .search(
                    [
                        ("parameter_id", "in", package.line_ids.parameter_id.ids),
                    ]
                )
            )
            by_parameter = {item.parameter_id.id: item for item in products}
            for part in package.line_ids:
                component = by_parameter.get(part.parameter_id.id)
                reason = self._product_unavailability(component)
                if component and not reason and not component.product_variant_ids[:1].active:
                    reason = self.env._("The product has no unique active catalog variant.")
                if reason:
                    return self.env._(
                        "Package component %(item)s is unavailable: %(reason)s",
                        item=part.parameter_id.display_name,
                        reason=reason,
                    )
        return False

    def _product_unavailability(self, product):
        if not product or not product.active or not product.sale_ok:
            return self.env._("The product is archived or is no longer sold.")
        variants = product.product_variant_ids.filtered("active")
        if len(variants) != 1:
            return self.env._("The product has no unique active catalog variant.")
        if product.parameter_id:
            prices = product.parameter_id.with_context(active_test=False).price_ids
            if not product.parameter_id.active or not prices or not all(prices.mapped("active")):
                return self.env._("The parameter or its catalog price is unavailable.")
        elif not product.service_package_id:
            return self.env._("The product no longer represents a parameter or package.")
        return False

    def _order_line_command(self):
        self.ensure_one()
        self._check_quantity()
        return Command.create(
            {
                "product_id": self.product_id.sudo().product_variant_ids.filtered("active").id,
                "product_uom_qty": self.quantity,
                "discount": 0,
            }
        )
