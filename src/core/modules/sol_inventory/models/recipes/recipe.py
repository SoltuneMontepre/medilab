from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.items import KIND_SOLUTION, TRACKING_CONTAINER
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_RECIPE, MODEL_RECIPE_LINE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_recipe as RecipeBase
else:
    RecipeBase = object

# The recipes saving their ingredients, which their own constraints check once they are all saved.
SAVING_LINES = "medilab_recipe_saving_lines"


# Công Thức Pha Chế
class Recipe(models.Model, RecipeBase):
    _name = MODEL_RECIPE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Recipe"
    _order = "code"
    _rec_names_search = ("code", "solution_item_id")
    _permission_actions = ("create", "edit", "archive", "delete")
    _audit_children = ("line_ids",)

    if not TYPE_CHECKING:
        # Unique code of the recipe, such as CTPC.0001; filled from a sequence when left empty.
        code = fields.Char(required=True, copy=False, index="trigram")
        # The prepared solution the recipe makes.
        solution_item_id = fields.Many2one(
            MODEL_PRODUCT,
            string="Solution",
            required=True,
            ondelete="restrict",
            domain=[("item_kind", "=", KIND_SOLUTION)],
        )
        # Quantity one preparation makes, in the solution's unit.
        yield_quantity = fields.Float(string="Yield per Preparation", digits="Product Unit", required=True)
        # The unit the yield is in: the solution's.
        uom_id = fields.Many2one(related="solution_item_id.uom_id")
        # Days the solution stays usable after it is prepared.
        shelf_life_days = fields.Integer(string="Shelf Life (Days)", required=True)
        # The ingredients and the amount of each that one preparation uses.
        line_ids = fields.One2many(MODEL_RECIPE_LINE, "recipe_id", string="Ingredients")
        # False when the recipe is archived.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a recipe must be unique.")
    _solution_unique = models.Constraint("UNIQUE(solution_item_id)", "Another recipe already makes this solution.")
    _yield_positive = models.Constraint("CHECK(yield_quantity > 0)", "The yield of a preparation must be above zero.")
    # An empty shelf life reads as 0, so 0 counts as no shelf life.
    _shelf_life_positive = models.Constraint(
        "CHECK(shelf_life_days >= 1)", "A recipe needs a shelf life of at least one day."
    )

    @api.depends("code", "solution_item_id.name")
    def _compute_display_name(self):
        for recipe in self:
            recipe.display_name = " – ".join(name for name in (recipe.code, recipe.solution_item_id.name) if name)

    def write(self, vals):
        # A save deletes the removed ingredients before it adds the new ones.
        recipes = self
        if "line_ids" in vals:
            recipes = self.with_context(**{SAVING_LINES: (*self.env.context.get(SAVING_LINES, ()), *self.ids)})
        return super(Recipe, recipes).write(vals)

    # The solution item is set on every create, so the check runs on recipes created without ingredients.
    @api.constrains("solution_item_id", "line_ids", "active")
    def _check_ingredients(self):
        """Refuse a recipe without ingredients, or with a solution or ingredient it cannot be prepared with."""
        for recipe in self:
            items = recipe.line_ids.item_id
            if not items:
                raise ValidationError(self.env._("%s needs at least one ingredient.", recipe.display_name))
            if recipe.solution_item_id.item_kind != KIND_SOLUTION:
                raise ValidationError(
                    self.env._(
                        "%(recipe)s cannot make %(item)s, which is not a prepared solution.",
                        recipe=recipe.display_name,
                        item=recipe.solution_item_id.display_name,
                    )
                )
            if recipe.solution_item_id in items:
                raise ValidationError(
                    self.env._("%s cannot use its own solution as an ingredient.", recipe.display_name)
                )
            # Prepared solutions are tracked by container too.
            untracked = items.filtered(lambda item: not item.item_kind or item.item_tracking != TRACKING_CONTAINER)
            if untracked:
                raise ValidationError(
                    self.env._(
                        "%(items)s cannot be ingredients of %(recipe)s: an ingredient is an item tracked by container "
                        "or a prepared solution.",
                        items=format_list(self.env, untracked.mapped("display_name")),
                        recipe=recipe.display_name,
                    )
                )
            archived = (recipe.solution_item_id | items).filtered(lambda item: not item.active)
            if recipe.active and archived:
                raise ValidationError(
                    self.env._(
                        "%(recipe)s cannot make or use archived items: %(items)s.",
                        recipe=recipe.display_name,
                        items=format_list(self.env, archived.mapped("display_name")),
                    )
                )
        self._check_no_loop()

    def _check_no_loop(self):
        """Refuse an ingredient prepared, through the recipes of the solutions it is made from, from the recipe's own
        solution."""
        recipes = self.sudo().with_context(active_test=False)
        for recipe in self:
            for ingredient in recipe.line_ids.item_id:
                reached = made_from = ingredient
                while made_from:
                    made_from = (
                        recipes.search(Domain("solution_item_id", "in", made_from.ids)).line_ids.item_id - reached
                    )
                    reached |= made_from
                if recipe.solution_item_id in reached:
                    raise ValidationError(
                        self.env._(
                            "%(recipe)s cannot use %(ingredient)s, which is prepared from %(solution)s, the solution "
                            "the recipe makes.",
                            recipe=recipe.display_name,
                            ingredient=ingredient.display_name,
                            solution=recipe.solution_item_id.display_name,
                        )
                    )

    def _check_outside_save(self):
        """Check the recipes whose ingredients changed other than by their own save."""
        saving = self.env.context.get(SAVING_LINES, ())
        self.exists().filtered(lambda recipe: recipe.id not in saving).sudo()._check_ingredients()
