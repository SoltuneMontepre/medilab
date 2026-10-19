from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_RECIPE, MODEL_RECIPE_LINE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Thành Phần Pha Chế
class RecipeLine(models.Model):
    _name = MODEL_RECIPE_LINE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Recipe Ingredient"
    _order = "recipe_id, id"
    _permission_actions = ("create", "edit", "delete")

    # The recipe the ingredient belongs to.
    recipe_id = fields.Many2one(MODEL_RECIPE, string="Recipe", required=True, ondelete="cascade")
    # The item one preparation uses: an item tracked by container, such as a chemical or another recipe's solution.
    item_id = fields.Many2one(
        MODEL_PRODUCT,
        string="Ingredient",
        required=True,
        ondelete="restrict",
        index=True,
        domain=[("item_kind", "!=", False), ("track_containers", "=", True)],
    )
    # Amount one preparation uses, in the item's unit.
    quantity = fields.Float(string="Amount", digits="Product Unit", required=True)
    # The unit the amount is in: the item's.
    uom_id = fields.Many2one(related="item_id.uom_id")

    _recipe_item_unique = models.Constraint(
        "UNIQUE(recipe_id, item_id)", "The recipe already uses this ingredient; change its amount instead."
    )
    _quantity_positive = models.Constraint("CHECK(quantity > 0)", "The amount of an ingredient must be above zero.")

    @api.constrains("recipe_id", "item_id")
    def _check_item(self):
        self.recipe_id._check_outside_save()

    def write(self, vals):
        # A line moved to another recipe leaves the one it came from.
        previous = self.recipe_id if "recipe_id" in vals else self.env[MODEL_RECIPE]
        result = super().write(vals)
        (previous - self.recipe_id)._check_outside_save()
        return result

    def unlink(self):
        recipes = self.recipe_id
        result = super().unlink()
        recipes._check_outside_save()
        return result
