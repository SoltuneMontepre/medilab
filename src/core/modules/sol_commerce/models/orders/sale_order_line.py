from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ORDER_SAMPLE,
    MODEL_PRODUCT_TEMPLATE,
    MODEL_SALE_ORDER,
    MODEL_SALE_ORDER_LINE,
)
from odoo.addons.sol_commerce.constants.orders import FROZEN_LINE_FIELDS, PORTAL_LOCKED_LINE_FIELDS
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN


# Dòng Đơn Hàng
class SaleOrderLine(models.Model):
    _name = MODEL_SALE_ORDER_LINE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SALE_ORDER_LINE]

    # The sample the line is tested on.
    sample_id = fields.Many2one(MODEL_ORDER_SAMPLE, ondelete="restrict", index="btree_not_null", copy=False)

    def _is_catalog_line(self):
        template = self.product_id.product_tmpl_id
        return bool(template.parameter_id or template.service_package_id)

    def _catalog_lines(self):
        """The parameters and packages the customer ordered; the parameters inside a package are not among them."""
        return self.filtered(lambda line: not line.display_type and not line.linked_line_id and line._is_catalog_line())

    def _frozen_lines(self):
        """Saved lines whose price, discount and taxes no longer follow the catalog.

        These are the lines of an order a quotation was sent for, and the parameters inside a package, which cost 0.
        """
        saved = self.filtered(lambda line: isinstance(line.id, int))
        quoted = saved.order_id.sudo().filtered("quotation_ids")
        return saved.filtered(lambda line: line.linked_line_id or line.order_id in quoted)

    def _compute_price_unit(self):
        return super(SaleOrderLine, self - self._frozen_lines())._compute_price_unit()

    def _compute_tax_ids(self):
        result = super(SaleOrderLine, self - self._frozen_lines())._compute_tax_ids()
        # Odoo gives a line without a product the company's default tax; a MediLab line takes the tax of its parameter or package.
        for line in self.filtered(lambda line: not line.product_id):
            line.tax_ids = False
        return result

    def _compute_discount(self):
        return super(SaleOrderLine, self - self._frozen_lines())._compute_discount()

    @api.constrains("product_uom_qty", "product_id", "display_type")
    def _check_catalog_quantity(self):
        for line in self._catalog_lines():
            if line.product_uom_qty < 1:
                raise ValidationError(self.env._("A catalog line needs a quantity of at least 1."))

    @api.constrains("sample_id", "order_id")
    def _check_sample_order(self):
        for line in self.filtered("sample_id"):
            if line.sample_id.order_id != line.order_id:
                raise ValidationError(self.env._("A line can only be tested on a sample of its own order."))

    def _content_lines(self):
        # The lines of a down payment are Odoo's own bookkeeping and follow the invoice, confirmed or not.
        return self.filtered(lambda line: not line.is_downpayment)

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals["order_id"] for vals in vals_list if vals.get("order_id") and not vals.get("is_downpayment")]
        self.env[MODEL_SALE_ORDER].browse(order_ids)._check_content_freeze()
        lines = super().create(vals_list)
        lines._add_package_parts()
        return lines

    def unlink(self):
        self._content_lines().order_id._check_content_freeze()
        return super().unlink()

    def write(self, vals):
        if PORTAL_LOCKED_LINE_FIELDS & set(vals) and self.env.user.share and not self.env.su:
            raise AccessError(self.env._("You cannot change the price of an order."))
        if FROZEN_LINE_FIELDS & set(vals):
            self._content_lines().order_id._check_content_freeze()
        result = super().write(vals)
        if "product_uom_qty" in vals:
            self._sync_package_part_quantities()
        parts = self.linked_line_ids if "sample_id" in vals else self.browse()
        if parts:
            parts.write({"sample_id": vals["sample_id"]})
        return result

    def _package_of(self):
        self.ensure_one()
        return self.product_id.product_tmpl_id.service_package_id.sudo()

    def _add_package_parts(self):
        """Give every package line one zero-priced line for each parameter the package includes."""
        parts = []
        for line in self._catalog_lines():
            package = line._package_of()
            if package and not line.linked_line_ids:
                parts += line._package_part_vals(package)
        if parts:
            self.create(parts)

    def _package_part_vals(self, package):
        self.ensure_one()
        products = (
            self.env[MODEL_PRODUCT_TEMPLATE]
            .sudo()
            .with_context(active_test=False)
            .search([("parameter_id", "in", package.line_ids.parameter_id.ids)])
        )
        variants = {product.parameter_id: product.product_variant_ids[:1] for product in products}
        vals = []
        for part in package.line_ids:
            variant = variants.get(part.parameter_id)
            if not variant:
                raise UserError(
                    self.env._("%s has no price, so the package cannot be ordered.", part.parameter_id.display_name)
                )
            vals.append(
                {
                    "order_id": self.order_id.id,
                    "product_id": variant.id,
                    "product_uom_qty": part.quantity * self.product_uom_qty,
                    "linked_line_id": self.id,
                    "sample_id": self.sample_id.id,
                    "sequence": self.sequence,
                    "price_unit": 0.0,
                }
            )
        return vals

    def _sync_package_part_quantities(self):
        for line in self._catalog_lines():
            package = line._package_of()
            for part in line.linked_line_ids:
                parameter = part.product_id.product_tmpl_id.parameter_id
                included = package.line_ids.filtered(lambda item, parameter=parameter: item.parameter_id == parameter)
                if included:
                    part.product_uom_qty = included.quantity * line.product_uom_qty

    def _copy_to_sample(self, sample):
        """Copy catalog lines onto the sample, keeping their price, discount and taxes."""
        return self.create(
            [
                {
                    "order_id": line.order_id.id,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.product_uom_qty,
                    "sample_id": sample.id,
                    "price_unit": line.price_unit,
                    "technical_price_unit": line.technical_price_unit,
                    "discount": line.discount,
                    "tax_ids": [Command.set(line.tax_ids.ids)],
                    "sequence": line.sequence,
                }
                for line in self
            ]
        )

    def _lock_catalog_price(self):
        for line in self._catalog_lines() - self._frozen_lines():
            price = line.product_id.product_tmpl_id.list_price
            # A price that differs from technical_price_unit is kept when the quantity changes.
            line.write({"price_unit": price, "technical_price_unit": 0.0 if price else 1.0})
