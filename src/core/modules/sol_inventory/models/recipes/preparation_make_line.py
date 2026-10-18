from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION_MAKE,
    MODEL_PREPARATION_MAKE_CONTAINER,
    MODEL_PREPARATION_MAKE_LINE,
    MODEL_PRODUCT,
    MODEL_STOCK_PACKAGE,
)


# Thành phần của một lần pha.
class PreparationMakeLine(models.TransientModel):
    _name = MODEL_PREPARATION_MAKE_LINE
    _description = "Preparation Ingredient"
    _order = "id"

    # The preparation wizard this ingredient belongs to.
    wizard_id = fields.Many2one(MODEL_PREPARATION_MAKE, required=True, ondelete="cascade")
    # The ingredient.
    item_id = fields.Many2one(MODEL_PRODUCT, string="Ingredient", required=True)
    # The unit of the amount: the ingredient's.
    uom_id = fields.Many2one(related="item_id.uom_id")
    # Amount the recipe asks for, in the ingredient's unit.
    recipe_quantity = fields.Float(string="Recipe Amount", digits="Product Unit", required=True)
    # Amount actually used. It starts at the recipe amount and can only be raised; the extra is wasted.
    quantity = fields.Float(string="Amount Used", digits="Product Unit", required=True)
    # Code read from a container's label; it adds the container and is not stored.
    container_scan = fields.Char(string="Scan Container", store=False)
    # Containers scanned for this ingredient, in scan order.
    container_ids = fields.One2many(MODEL_PREPARATION_MAKE_CONTAINER, "line_id", string="Containers")
    # Codes of the scanned containers, in scan order.
    container_codes = fields.Char(string="Containers", compute="_compute_container_codes")

    @api.depends("container_ids.container_id", "container_ids.sequence")
    def _compute_container_codes(self):
        for line in self:
            line.container_codes = ", ".join(line.container_ids.container_id.mapped("display_name"))

    @api.onchange("container_scan")
    def _onchange_container_scan(self):
        code = (self.container_scan or "").strip()
        if not code:
            return
        container = self.env[MODEL_STOCK_PACKAGE]._find_by_code(code)
        if container in self.container_ids.container_id:
            raise UserError(self.env._("%s is already on this ingredient.", container.display_name))
        sequence = max(self.container_ids.mapped("sequence") or [0]) + 1
        self.container_ids = [Command.create({"container_id": container.id, "sequence": sequence})]
        self.container_scan = False
