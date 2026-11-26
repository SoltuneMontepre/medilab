from typing import TYPE_CHECKING, cast

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
from odoo.addons.sol_laboratory.constants.catalog import WAY_BY_METHOD
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_SAMPLING_REQUIREMENT,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order_line as SaleOrderLineBase
else:
    SaleOrderLineBase = object


def _sampling_summary(rows):
    """The amount and container of each sampling row, and the distinct preservations, each as one text or False."""
    volumes = []
    preservations = []
    for row in rows:
        amount = f"{row['amount']:g} {row['unit'].name}" if row.get("unit") else f"{row['amount']:g}"
        container = row["requirements"][:1].container_type
        volumes.append(f"{amount} ({container})" if container else amount)
        preservation = row["requirements"][:1].preservation
        if preservation and preservation not in preservations:
            preservations.append(preservation)
    return ", ".join(volumes) or False, ", ".join(preservations) or False


# Dòng Đơn Hàng
class SaleOrderLine(models.Model, SaleOrderLineBase):
    _name = MODEL_SALE_ORDER_LINE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SALE_ORDER_LINE]

    if not TYPE_CHECKING:
        # The sample the line is tested on.
        sample_id = fields.Many2one(MODEL_ORDER_SAMPLE, ondelete="restrict", index="btree_not_null", copy=False)
        # Expected physical sample count calculated from sampling requirements and order quantity.
        expected_sample_count = fields.Integer(string="Sample Quantity", compute="_compute_expected_sample_summary")
        # Concise sample volume and container summary shown inline on the order line.
        expected_sample_summary = fields.Char(string="Sample Volume", compute="_compute_expected_sample_summary")
        # Sample preservation condition shown when opening the order line form.
        sampling_preservation = fields.Char(string="Preservation", compute="_compute_expected_sample_summary")
        # The sample type the line is tested on: chosen, or the type of its sample; a package's parameter takes its
        # package's.
        sample_type_id = fields.Many2one(
            MODEL_SAMPLE_TYPE,
            compute="_compute_sample_type_id",
            recursive=True,
            store=True,
            readonly=False,
            ondelete="restrict",
            index="btree_not_null",
            domain="[('id', 'in', offered_sample_type_ids)]",
        )
        # The sample types every parameter of the line can be ordered on.
        offered_sample_type_ids = fields.Many2many(
            MODEL_SAMPLE_TYPE, string="Offered Sample Types", compute="_compute_offered_sample_type_ids"
        )
        # The way of testing the line's parameter is tested by: chosen, or the parameter's default on the sample type
        # when it is available. Empty on a package line, whose parameters each carry their own.
        parameter_method_id = fields.Many2one(
            MODEL_PARAMETER_METHOD,
            string="Way of Testing",
            compute="_compute_parameter_method_id",
            store=True,
            readonly=False,
            ondelete="restrict",
            domain="[('id', 'in', offered_method_ids)]",
        )
        # The ways of testing that can be chosen for the line's parameter on its sample type, one per method.
        offered_method_ids = fields.Many2many(
            MODEL_PARAMETER_METHOD, string="Offered Ways of Testing", compute="_compute_offered_method_ids"
        )
        # Why the default way of testing of the line's parameters on the sample's type is unavailable, and the ways to
        # choose instead; empty when every default is available.
        default_way_notice = fields.Char(string="Default Way", compute="_compute_default_way_notice")

    def _is_package_part(self):
        return bool(self.linked_line_id or self.linked_virtual_id)

    def _is_catalog_line(self):
        template = self.product_id.product_tmpl_id or self.product_template_id
        return bool(template.parameter_id or template.service_package_id)

    def _catalog_lines(self):
        """The parameters and packages the customer ordered; the parameters inside a package are not among them."""
        return self.filtered(
            lambda line: not line.display_type and not line._is_package_part() and line._is_catalog_line()
        )

    def _frozen_lines(self):
        """Lines whose price, discount and taxes no longer follow the catalog.

        These are the lines of an order a quotation was sent for, and the parameters inside a package, which cost 0.
        """
        saved = self.filtered(lambda line: isinstance(line.id, int))
        quoted = saved.order_id.sudo().filtered("quotation_ids")
        return self.filtered(lambda line: line._is_package_part() or (line in saved and line.order_id in quoted))

    def _compute_price_unit(self):
        return super(SaleOrderLine, self - self._frozen_lines())._compute_price_unit()

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

    @api.constrains("sample_id", "sample_type_id")
    def _check_sample_type_of_sample(self):
        for line in self.filtered("sample_id"):
            if line.sample_type_id != line.sample_id.sample_type_id:
                raise ValidationError(
                    self.env._(
                        "%(item)s is tested on %(sample)s, so its sample type is %(sample_type)s.",
                        item=line.product_id.display_name,
                        sample=line.sample_id.display_name,
                        sample_type=line.sample_id.sample_type_id.display_name,
                    )
                )

    @api.depends(
        "product_id",
        "product_template_id",
        "product_uom_qty",
        "sample_type_id",
        "parameter_method_id",
        "parameter_method_id.method_id",
        "linked_line_ids.parameter_method_id",
        "linked_line_ids.parameter_method_id.method_id",
    )
    def _compute_expected_sample_summary(self):
        requirements = self.env[MODEL_SAMPLING_REQUIREMENT].sudo()
        for line in self:
            if line._is_package_part():
                line.expected_sample_count = 0
                line.expected_sample_summary = False
                line.sampling_preservation = False
                continue
            ways = (line._package_parts() | line)._resolved_ways()
            methods = self.env[MODEL_PARAMETER_METHOD].concat(ways).sudo().method_id
            if not line.sample_type_id or not methods:
                line.expected_sample_count = 0
                line.expected_sample_summary = False
                line.sampling_preservation = False
                continue
            rows, _missing = requirements._sampling_rows(line.sample_type_id, methods)
            groups = {row["group"] for row in rows}
            line.expected_sample_count = max(int(line.product_uom_qty), 1) * len(groups) if groups else 0
            line.expected_sample_summary, line.sampling_preservation = _sampling_summary(rows)

    @api.onchange("product_template_id")
    def _onchange_product_template_id(self):
        super()._onchange_product_template_id()
        if self.product_template_id and self.product_id.product_tmpl_id != self.product_template_id:
            self.product_id = self.product_template_id.product_variant_id

    @api.onchange("product_template_id", "product_id")
    def _onchange_product_sample_type(self):
        if self._is_package_part() or self.sample_id or not self._parameters():
            return
        choices = self._sample_type_choices()
        if self.sample_type_id not in choices:
            self.sample_type_id = choices if len(choices) == 1 else False
        elif not self.sample_type_id and len(choices) == 1:
            self.sample_type_id = choices

    @api.onchange("sample_type_id")
    def _onchange_sample_type_detach_sample(self):
        if self.sample_id and self.sample_id.sample_type_id != self.sample_type_id:
            self.sample_id = False

    @api.depends("product_id", "product_template_id", "order_id.partner_id")
    def _compute_offered_sample_type_ids(self):
        # A line without a parameter or package yet offers every sample type something on sale can be ordered on, so
        # the sample type can be chosen first.
        catalog = None
        for line in self:
            if line._parameters():
                line.offered_sample_type_ids = line._sample_type_choices()
                continue
            if catalog is None:
                catalog = self.env[MODEL_PRODUCT_TEMPLATE]._orderable_sample_types_of_catalog()
            line.offered_sample_type_ids = catalog

    @api.depends("sample_id.sample_type_id", "linked_line_id.sample_type_id")
    def _compute_sample_type_id(self):
        for line in self:
            line.sample_type_id = (
                line.sample_id.sample_type_id or line.linked_line_id.sample_type_id or line.sample_type_id
            )

    @api.depends("product_id", "sample_type_id", "order_id.partner_id")
    def _compute_offered_method_ids(self):
        for line in self:
            line.offered_method_ids = line._offered_ways()

    def _offered_ways(self):
        """The ways of testing the line's parameter can be chosen from on its sample type; none without both. A way the
        customer's own company tests as a subcontractor is never offered."""
        self.ensure_one()
        parameter = self._own_parameter()
        if not parameter or not self.sample_type_id:
            return self.env[MODEL_PARAMETER_METHOD]
        return parameter._offered_ways(self.sample_type_id, self.order_id.partner_id)

    @api.depends("product_id", "sample_type_id", "order_id.partner_id")
    def _compute_parameter_method_id(self):
        # A chosen way stays while it is still offered; otherwise only an available default is filled in, since
        # another way is never chosen silently.
        for line in self:
            parameter = line._own_parameter()
            if not parameter or not line.sample_type_id:
                line.parameter_method_id = False
                continue
            offered = line._offered_ways()
            if line.parameter_method_id not in offered:
                default = parameter._default_way(line.sample_type_id)
                line.parameter_method_id = default & offered

    @api.depends("product_id", "sample_type_id")
    def _compute_default_way_notice(self):
        for line in self:
            sample_type = line.sample_type_id
            notices = (
                [
                    parameter.with_context(**{WAY_BY_METHOD: True})._default_way_notice(sample_type)
                    for parameter in line._parameters()
                ]
                if sample_type
                else []
            )
            line.default_way_notice = " ".join(notice for notice in notices if isinstance(notice, str)) or False

    @api.constrains("sample_type_id", "product_id")
    def _check_offered_on_sample(self):
        for line in self._catalog_lines().filtered("sample_type_id"):
            sample_type = line.sample_type_id
            refusals = [
                parameter.with_context(**{WAY_BY_METHOD: True})._order_refusal(sample_type)
                for parameter in line._parameters()
            ]
            refusals = [refusal for refusal in refusals if refusal]
            if refusals:
                raise ValidationError(" ".join(refusals))

    @api.constrains("parameter_method_id", "sample_type_id", "product_id")
    def _check_way_applies(self):
        for line in self.filtered("parameter_method_id"):
            way = line.parameter_method_id.sudo()
            if way.parameter_id != line._own_parameter() or not way._applicability(line.sample_type_id):
                raise ValidationError(
                    self.env._(
                        "%(way)s does not test %(item)s on %(sample_type)s.",
                        way=way.display_name,
                        item=line.product_id.display_name,
                        sample_type=line.sample_type_id.display_name or self.env._("no sample type"),
                    )
                )

    def _template(self):
        self.ensure_one()
        return (self.product_id.product_tmpl_id or self.product_template_id).sudo()

    def _parameters(self):
        # The parameter of a parameter line, or the parameters a package includes; read from the shared catalog.
        return self._template()._sold_parameters()

    def _own_parameter(self):
        # The parameter a parameter line or a package's parameter tests; empty on a package line.
        return self._template().parameter_id

    def _package_parts(self):
        """The parameter lines linked to this package line, whether saved or still in memory."""
        self.ensure_one()
        if self.linked_line_ids:
            return self.linked_line_ids
        pool = self.order_id.product_line_ids | self.order_id.order_line
        return pool._get_linked_lines_by_line().get(self, self.browse())

    def _sample_type_choices(self):
        """The sample types every parameter of the line can be ordered on."""
        self.ensure_one()
        return self._template()._orderable_sample_types(self.order_id.partner_id)

    def _preselect_sample_type(self):
        """Give a line new in the cart a sample type to start from, so the expected samples show at once: the one the
        cart's other items are already tested on when this item can be too, else the first it can be ordered on. The
        customer can change it in the cart."""
        self.ensure_one()
        choices = self._sample_type_choices()
        if self.sample_type_id or not choices:
            return
        used = self.order_id._catalog_lines().filtered("sample_type_id").sample_type_id
        self.sudo().sample_type_id = (used & choices)[:1] or choices[:1]

    def _set_cart_selection(self, sample_type_id=None, parameter_method_id=None):
        """Set the sample type or the way of testing the customer chose in the cart, refusing one not offered."""
        self.ensure_one()
        vals = {}
        if sample_type_id is not None:
            sample_type = self.env[MODEL_SAMPLE_TYPE].sudo().browse(sample_type_id)
            if self.linked_line_id or sample_type not in self._sample_type_choices():
                raise UserError(
                    self.env._("Choose one of the sample types offered for %s.", self.product_id.display_name)
                )
            vals["sample_type_id"] = sample_type.id
        if parameter_method_id is not None:
            way = self.env[MODEL_PARAMETER_METHOD].sudo().browse(parameter_method_id)
            if way not in self.offered_method_ids:
                raise UserError(
                    self.env._("Choose one of the ways of testing offered for %s.", self.product_id.display_name)
                )
            vals["parameter_method_id"] = way.id
        self.sudo().write(vals)

    def _check_ways_can_be_sent(self):
        """Refuse sending while a parameter has no way of testing or its way can no longer be offered."""
        missing = self.filtered(lambda line: not line.parameter_method_id)
        if missing:
            raise UserError(
                self.env._(
                    "Choose a way of testing for these items before sending the quotation:\n%s",
                    "\n".join(missing._way_label()),
                )
            )
        unavailable = self.filtered(lambda line: line.parameter_method_id not in line._offered_ways())
        if unavailable:
            raise UserError(
                self.env._(
                    "These ways of testing can no longer be offered; choose another before sending the quotation:\n%s",
                    "\n".join(
                        f"{label}: {line.parameter_method_id.display_name}. "
                        f"{line.parameter_method_id.sudo()._unavailable_reason() or ''}".strip()
                        for line, label in zip(unavailable, unavailable._way_label(), strict=True)
                    ),
                )
            )

    def _way_label(self):
        # Each line's parameter, after its package when it is a package's parameter.
        return [
            " – ".join(
                name for name in (line.linked_line_id.product_id.display_name, line.product_id.display_name) if name
            )
            for line in self
        ]

    def _test_values(self):
        # The parameter as a sample test takes it.
        self.ensure_one()
        return {
            "parameter_id": self._own_parameter().id,
            "quantity": self.product_uom_qty,
            "parameter_method_id": self.parameter_method_id.id,
        }

    def _way_lines(self):
        """The lines that are tested by a way of testing: parameter lines and the parameters inside a package."""
        return self.filtered(
            lambda line: not line.display_type and not line.is_downpayment and bool(line._own_parameter())
        )

    def _resolved_ways(self):
        """Ways of testing across parameter lines and not-yet-expanded package lines while editing."""
        ways = []
        for line in self:
            if line.display_type or line.is_downpayment:
                continue
            if line._own_parameter():
                if line.parameter_method_id:
                    ways.append(line.parameter_method_id)
                continue
            ways += line._package_default_ways()
        return ways

    def _package_default_ways(self):
        """The default ways of testing, when offered on the line's sample type, of the parameters of a package line that
        is not expanded yet."""
        self.ensure_one()
        package = self._package_of()
        if not package or self._package_parts() or not self.sample_type_id:
            return []
        partner = self.order_id.partner_id
        ways = []
        for parameter in package.line_ids.parameter_id:
            way = parameter._default_way(self.sample_type_id) & parameter._offered_ways(self.sample_type_id, partner)
            if way:
                ways.append(way)
        return ways

    def _content_lines(self):
        # The lines of a down payment are Odoo's own bookkeeping and follow the invoice, confirmed or not.
        return self.filtered(lambda line: not line.is_downpayment)

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals["order_id"] for vals in vals_list if vals.get("order_id") and not vals.get("is_downpayment")]
        self.env[MODEL_SALE_ORDER].browse(order_ids)._check_content_freeze()
        # A package's parameter lines expanded on the order form are created after their package and linked to it on
        # creation, since Sales may not be allowed to write lines of an order they are only creating.
        parents = [vals for vals in vals_list if not vals.get("linked_virtual_id")]
        lines = super().create(parents) if parents else self.browse()
        by_virtual = {line.virtual_id: line.id for line in lines if line.virtual_id}
        parts = []
        for vals in vals_list:
            if vals.get("linked_virtual_id"):
                linked = by_virtual.get(vals["linked_virtual_id"])
                parts.append({**vals, "linked_line_id": linked} if linked else vals)
        if parts:
            lines |= super().create(parts)
            # The packages read their parameter lines while being created, before these existed.
            lines.invalidate_recordset(["linked_line_ids"])
        lines._add_package_parts()
        return lines

    def unlink(self):
        self._content_lines().order_id._check_content_freeze()
        if not self.env.context.get("_replacing_package_parts"):
            orphaned = self.filtered(
                lambda line: bool(
                    line.linked_line_id
                    and line.linked_line_id not in self
                    and line.linked_line_id.exists()
                    and line.linked_line_id._package_of()
                )
            )
            if orphaned:
                raise UserError(
                    self.env._(
                        "A service package is ordered as a whole; remove the package instead of one of its parameters."
                    )
                )
        return super(SaleOrderLine, self | self.linked_line_ids).unlink()

    def write(self, vals):
        if set(vals) == {"linked_line_id"}:
            # Odoo links every new line to its package again after creating it; a link that is already set is not a
            # change, so it needs no write access to the order.
            changed = self.filtered(lambda line: line.linked_line_id.id != vals["linked_line_id"])
            if changed != self:
                return changed.write(vals) if changed else True
        if PORTAL_LOCKED_LINE_FIELDS & set(vals) and self.env.user.share and not self.env.su:
            raise AccessError(self.env._("You cannot change the price of an order."))
        self._check_write_content_freeze(vals)
        replaced = (
            self.filtered(lambda line: bool(line.linked_line_ids and line.product_id.id != vals["product_id"]))
            if "product_id" in vals
            else self.browse()
        )
        if "sample_type_id" in vals and "sample_id" not in vals:
            mismatched = self.filtered(
                lambda line: bool(line.sample_id and line.sample_id.sample_type_id.id != vals["sample_type_id"])
            )
            if mismatched:
                super(SaleOrderLine, cast("SaleOrderLine", mismatched)).write({"sample_id": False})
                if mismatched.linked_line_ids:
                    super(SaleOrderLine, cast("SaleOrderLine", mismatched.linked_line_ids)).write({"sample_id": False})
        result = super().write(vals)
        if replaced:
            replaced.with_context(_replacing_package_parts=True).linked_line_ids.unlink()
            replaced._add_package_parts()
        if "product_uom_qty" in vals:
            self._sync_package_part_quantities()
        parts = self.linked_line_ids if "sample_id" in vals else self.browse()
        if parts:
            parts.write({"sample_id": vals["sample_id"]})
        return result

    def _check_write_content_freeze(self, vals):
        """Refuse writing vals when it changes the content of an order that is frozen."""
        if FROZEN_LINE_FIELDS & set(vals):
            # A down payment that would become content counts as content too.
            lines = self if "is_downpayment" in vals else self._content_lines()
            lines.order_id._check_content_freeze()
        if vals.get("order_id") and self._content_lines():
            # A line moved onto another order changes that order's content too.
            self.env[MODEL_SALE_ORDER].browse(vals["order_id"])._check_content_freeze()

    def _package_of(self):
        return self._template().service_package_id.sudo()

    def _add_package_parts(self):
        """Give every package line one zero-priced line for each parameter the package includes."""
        parts = []
        for line in self._catalog_lines():
            package = line._package_of()
            # Sales may not yet be allowed to read the lines of an order they are creating.
            if package and not line.sudo().linked_line_ids:
                parts += line._package_part_vals(package)
        if parts:
            self.create(parts)
            for order in self.order_id:
                order.sudo()._align_package_part_sequences()

    def _package_part_variants(self, package):
        products = (
            self.env[MODEL_PRODUCT_TEMPLATE]
            .sudo()
            .with_context(active_test=False)
            .search([("parameter_id", "in", package.line_ids.parameter_id.ids)])
        )
        variants = {product.parameter_id: product.product_variant_ids[:1] for product in products}
        chosen = []
        for part in package.line_ids:
            variant = variants.get(part.parameter_id)
            if not variant:
                raise UserError(
                    self.env._("%s has no price, so the package cannot be ordered.", part.parameter_id.display_name)
                )
            chosen.append((part, variant))
        return chosen

    def _package_part_vals(self, package):
        self.ensure_one()
        return [
            {
                "order_id": self.order_id.id,
                "product_id": variant.id,
                "product_uom_qty": part.quantity * self.product_uom_qty,
                "linked_line_id": self.id,
                "sample_id": self.sample_id.id,
                "sample_type_id": self.sample_type_id.id,
                "sequence": self.sequence,
                "price_unit": 0.0,
                "tax_ids": [Command.clear()],
            }
            for part, variant in self._package_part_variants(package)
        ]

    def _onchange_package_part_vals(self, package):
        """Values for the in-memory parameter lines expanded when a package is selected on the order form."""
        self.ensure_one()
        return [
            {
                "product_id": variant.id,
                "product_template_id": variant.product_tmpl_id.id,
                "product_uom_qty": part.quantity * self.product_uom_qty,
                "linked_line_id": self._origin.id if self._origin else False,
                "linked_virtual_id": self.virtual_id if not self._origin else False,
                "sample_type_id": self.sample_type_id.id,
                "sequence": self.sequence,
                "price_unit": 0.0,
                "tax_ids": [Command.clear()],
            }
            for part, variant in self._package_part_variants(package)
        ]

    def _sync_package_part_quantities(self):
        for line in self._catalog_lines():
            package = line._package_of()
            for part in line.linked_line_ids:
                parameter = part.product_id.product_tmpl_id.parameter_id
                included = package.line_ids.filtered(lambda item, parameter=parameter: item.parameter_id == parameter)
                if included:
                    part.product_uom_qty = included.quantity * line.product_uom_qty

    def _copy_to_sample(self, sample):
        """Copy catalog lines onto the sample, keeping their price, discount, taxes and ways of testing."""
        copies = self.create(
            [
                {
                    "order_id": line.order_id.id,
                    "product_id": line.product_id.id,
                    "product_uom_qty": line.product_uom_qty,
                    "sample_id": sample.id,
                    "parameter_method_id": line.parameter_method_id.id,
                    "price_unit": line.price_unit,
                    "technical_price_unit": line.technical_price_unit,
                    "discount": line.discount,
                    "tax_ids": [Command.set(persisted_ids(line.tax_ids))],
                    "sequence": line.sequence,
                }
                for line in self
            ]
        )
        for line, copy in zip(self, copies, strict=True):
            chosen = {part.product_id: part.parameter_method_id for part in line.linked_line_ids}
            for part in copy.linked_line_ids:
                part.parameter_method_id = chosen.get(part.product_id) or part.parameter_method_id
        return copies

    def _lock_catalog_price(self):
        for line in self._catalog_lines() - self._frozen_lines():
            price = line.product_id.product_tmpl_id.list_price
            # A price that differs from technical_price_unit is kept when the quantity changes.
            line.write({"price_unit": price, "technical_price_unit": 0.0 if price else 1.0})
