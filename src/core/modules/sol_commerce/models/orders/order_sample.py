from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_SAMPLE, MODEL_SALE_ORDER, MODEL_SALE_ORDER_LINE
from odoo.addons.sol_commerce.constants.orders import FROZEN_SAMPLE_FIELDS
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_SAMPLE_TYPE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_order_sample as OrderSampleBase
else:
    OrderSampleBase = object


# Mẫu Đơn Hàng
class OrderSample(models.Model, OrderSampleBase):
    _name = MODEL_ORDER_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Order Sample"
    _order = "order_id, sequence, id"
    _rec_name = "customer_sample_name"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The order.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade", index=True)
        # Name the customer gives the sample, such as "Lavie bottled water 1 L".
        customer_sample_name = fields.Char(string="Customer's Sample Name", required=True)
        # The sample type (nền mẫu), such as bottled drinking water.
        sample_type_id = fields.Many2one(MODEL_SAMPLE_TYPE, required=True, ondelete="restrict")
        # Whether the sample is solid, liquid, gas or semi-solid.
        physical_state = fields.Selection(
            [("solid", "Solid"), ("liquid", "Liquid"), ("gas", "Gas"), ("semi_solid", "Semi-solid")], required=True
        )
        # The regulation the sample's results are compared with; empty when none.
        regulation_id = fields.Many2one(MODEL_REGULATION, ondelete="restrict")
        # Why the sample keeps a regulation that is no longer in force; empty while it is.
        regulation_notice = fields.Char(string="Regulation Notice", compute="_compute_regulation_notice")
        # Position of the sample in the order.
        sequence = fields.Integer(default=10)
        # Lines tested on the sample.
        line_ids = fields.One2many(MODEL_SALE_ORDER_LINE, "sample_id", string="Lines")

    @api.depends("regulation_id.valid_until")
    def _compute_regulation_notice(self):
        for sample in self:
            sample.regulation_notice = sample.regulation_id._expiry_notice() if sample.regulation_id else False

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env[MODEL_SALE_ORDER].browse([vals["order_id"] for vals in vals_list if vals.get("order_id")])
        orders._check_content_freeze()
        samples = super().create(vals_list)
        samples._check_regulation()
        return samples

    def write(self, vals):
        if FROZEN_SAMPLE_FIELDS & set(vals):
            self.order_id._check_content_freeze()
        result = super().write(vals)
        if "sample_type_id" in vals:
            self.line_ids._check_offered_on_sample()
        if {"regulation_id", "sample_type_id"} & set(vals):
            self._check_regulation()
        return result

    def _check_regulation(self):
        # A regulation chosen for a sample, or a sample type chosen for a sample with one, is a new selection.
        for sample in self.filtered("regulation_id"):
            sample.regulation_id._check_selectable(sample.sample_type_id)

    def unlink(self):
        self.order_id._check_content_freeze()
        return super().unlink()

    def copy_sample(self):
        """Duplicate each sample and its catalog lines on the same order."""
        copies = self.browse()
        for sample in self:
            copy = sample.copy({"sequence": sample.sequence + 1})
            sample.line_ids._catalog_lines()._copy_to_sample(copy)
            copies |= copy
        return copies

    def _test_request_values(self):
        """The sample as a test request takes it: a package carries its parameters, any other line is one parameter."""
        self.ensure_one()
        lines = []
        for line in self.line_ids._catalog_lines():
            template = line.product_id.product_tmpl_id
            if template.service_package_id:
                parameters = [
                    {"parameter_id": part.product_id.product_tmpl_id.parameter_id.id, "quantity": part.product_uom_qty}
                    for part in line.linked_line_ids
                ]
                lines.append({"parameters": parameters})
            else:
                lines.append({"parameter_id": template.parameter_id.id, "quantity": line.product_uom_qty})
        return {
            "customer_sample_name": self.customer_sample_name,
            "sample_type_id": self.sample_type_id.id,
            "physical_state": self.physical_state,
            "regulation_id": self.regulation_id.id,
            "lines": lines,
        }

    def action_copy_sample(self):
        """The Copy button: a button result must be serializable, so it does not return the copies."""
        self.copy_sample()
        return True
