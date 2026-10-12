from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_SAMPLE, MODEL_SALE_ORDER, MODEL_SALE_ORDER_LINE
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_REGULATION, MODEL_SAMPLE_TYPE


# Mẫu Đơn Hàng
class OrderSample(models.Model):
    _name = MODEL_ORDER_SAMPLE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Order Sample"
    _order = "order_id, sequence, id"
    _rec_name = "customer_sample_name"
    _permission_actions = ("read", "create", "edit", "delete")

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
    # Position of the sample in the order.
    sequence = fields.Integer(default=10)
    # Lines tested on the sample.
    line_ids = fields.One2many(MODEL_SALE_ORDER_LINE, "sample_id", string="Lines")

    def copy_sample(self):
        """Duplicate each sample and its catalog lines on the same order."""
        copies = self.browse()
        for sample in self:
            copy = sample.copy({"sequence": sample.sequence + 1})
            sample.line_ids._catalog_lines()._copy_to_sample(copy)
            copies |= copy
        return copies
