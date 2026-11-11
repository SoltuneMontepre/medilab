from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_METHOD_CONSUMPTION, MODEL_PRODUCT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN, MODEL_TESTING_METHOD

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_method_consumption as MethodConsumptionBase
else:
    MethodConsumptionBase = object


# Định Mức Tiêu Hao
class MethodConsumption(models.Model, MethodConsumptionBase):
    _name = MODEL_METHOD_CONSUMPTION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Use per Test"
    _order = "method_id, product_id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The testing method.
        method_id = fields.Many2one(MODEL_TESTING_METHOD, string="Testing Method", required=True, ondelete="cascade")
        # The item one test of the method uses.
        product_id = fields.Many2one(
            MODEL_PRODUCT,
            string="Item",
            required=True,
            ondelete="restrict",
            index=True,
            domain=[("item_kind", "!=", False)],
        )
        # Quantity one test uses, in the item's unit.
        quantity = fields.Float(digits="Product Unit", required=True)
        # The unit the quantity is in: the item's.
        uom_id = fields.Many2one(related="product_id.uom_id")

    _method_item_unique = models.Constraint(
        "UNIQUE(method_id, product_id)", "The method already uses this item; change its quantity instead."
    )
    _quantity_positive = models.Constraint("CHECK(quantity > 0)", "The quantity one test uses must be above zero.")
