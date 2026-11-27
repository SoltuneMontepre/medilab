from typing import TYPE_CHECKING
from uuid import uuid4

from odoo import api, fields, models
from odoo.fields import Command

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SALE_ORDER_LINE
from odoo.addons.sol_commerce.constants.xml_ids import DISCOUNT_PRODUCT

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderBase
else:
    SaleOrderBase = object


# Đơn Hàng: the order form lists the ordered parameters and packages apart from the down payments.
class SaleOrder(models.Model, SaleOrderBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Every line of the order, down payments included.
        order_line = fields.One2many(string="All Order Lines")
        # The ordered parameters and packages: every line but Odoo's down payment section and lines.
        product_line_ids = fields.One2many(
            MODEL_SALE_ORDER_LINE,
            "order_id",
            string="Order Lines",
            domain=[("is_downpayment", "=", False)],
            copy=False,
        )
        # The priced lines of the quotation: parameters, whole packages and quotation discounts, without package parts.
        quoted_line_ids = fields.One2many(
            MODEL_SALE_ORDER_LINE,
            "order_id",
            string="Quoted Lines",
            domain=[("is_downpayment", "=", False), ("linked_line_id", "=", False)],
            copy=False,
        )
        # The down payment lines Odoo adds when an advance invoice is created, without their section.
        downpayment_line_ids = fields.One2many(
            MODEL_SALE_ORDER_LINE,
            "order_id",
            string="Advance payments",
            domain=[("is_downpayment", "=", True), ("display_type", "=", False)],
            readonly=True,
            copy=False,
        )

    @api.onchange("product_line_ids")
    def _onchange_product_line_ids(self):
        """Expand package parameters, sync their sample types and give the edited lines back to Odoo's order lines."""
        self._sync_onchange_package_lines()
        self.order_line = self.product_line_ids | self.order_line.filtered("is_downpayment")

    def _grouped_package_lines(self):
        """Partition product_line_ids into top-level parents, their linked parameter rows and any orphaned parts."""
        lines = self.product_line_ids
        parents = lines.filtered(lambda line: not line._is_package_part())
        by_origin = {line._origin: line for line in parents if line._origin}
        by_virtual = {line.virtual_id: line for line in parents if line.virtual_id}
        linked = {parent: lines.browse() for parent in parents}
        orphans = lines.browse()
        for child in lines.filtered(lambda line: line._is_package_part()):
            parent = (
                by_origin.get(child.linked_line_id._origin)
                if child.linked_line_id._origin
                else by_virtual.get(child.linked_virtual_id or "")
            )
            if parent is not None:
                linked[parent] |= child
            else:
                orphans |= child
        return parents, linked, orphans

    def _sync_onchange_package_lines(self):
        parents, linked, removed = self._grouped_package_lines()
        created = []
        for parent in parents:
            package = parent._package_of()
            parts = linked[parent]
            if not package:
                removed |= parts
                continue
            same_saved = bool(parts and parent._origin and parent.product_id == parent._origin.product_id)
            same_unsaved = bool(
                parts
                and not parent._origin
                and [part._own_parameter() for part in parts] == list(package.line_ids.parameter_id)
            )
            if same_saved or same_unsaved:
                for part in parts:
                    parameter = part._own_parameter()
                    included = package.line_ids.filtered(lambda item, p=parameter: item.parameter_id == p)[:1]
                    if part.sample_type_id != parent.sample_type_id:
                        part.sample_type_id = parent.sample_type_id
                    if included and part.product_uom_qty != included.quantity * parent.product_uom_qty:
                        part.product_uom_qty = included.quantity * parent.product_uom_qty
                continue
            removed |= parts
            if not parent._origin and not parent.virtual_id:
                parent.virtual_id = f"medilab_pkg_{uuid4().hex}"
            created.extend(Command.create(vals) for vals in parent._onchange_package_part_vals(package))

        if removed:
            self.product_line_ids -= removed
        if created:
            self.product_line_ids = created
        self._align_package_part_sequences()
        if self.product_line_ids:
            self.product_line_ids._compute_expected_sample_summary()

    def _align_package_part_sequences(self):
        """Keep every package's parameter rows right below their package row."""
        parents, linked, _orphans = self._grouped_package_lines()
        if not any(linked.values()):
            return
        ordered = []
        for index, parent in enumerate(parents):
            ordered.append((parent.sequence, index, parent, linked[parent]))
        ordered.sort(key=lambda entry: (entry[0], entry[1]))
        expected = []
        for _seq, _idx, parent, parts in ordered:
            expected.append(parent)
            expected.extend(parts)
        current = list(
            self.product_line_ids.sorted(
                lambda line: (
                    line.sequence,
                    line.id if isinstance(line.id, int) else 0,
                    1 if line._is_package_part() else 0,
                )
            )
        )
        if current != expected:
            for sequence, line in enumerate(expected, start=10):
                if line.sequence != sequence:
                    line.sequence = sequence

    def _discount_lines(self):
        """The discount lines given on the whole quotation."""
        discount = self.env.ref(DISCOUNT_PRODUCT)
        return self.order_line.filtered(lambda line: line.product_id == discount)
