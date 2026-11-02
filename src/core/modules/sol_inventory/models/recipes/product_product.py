from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_RECIPE

if TYPE_CHECKING:
    from medilab_model_types import Model_product_product as ProductProductBase
else:
    ProductProductBase = object


# Vật Tư
class ProductProduct(models.Model, ProductProductBase):
    _inherit = MODEL_PRODUCT

    @api.constrains("item_kind", "tracking", "track_containers")
    def _check_recipes_kept(self):
        # An active recipe keeps making a prepared solution from items tracked by container.
        self._active_recipes()._check_ingredients()

    def _check_archivable(self):
        result = super()._check_archivable()
        recipes = self._active_recipes()
        if recipes:
            raise UserError(
                self.env._(
                    "%(items)s cannot be archived while active recipes make or use them: %(recipes)s.",
                    items=format_list(
                        self.env, ((recipes.solution_item_id | recipes.line_ids.item_id) & self).mapped("display_name")
                    ),
                    recipes=format_list(self.env, recipes.mapped("display_name")),
                )
            )
        return result

    def _active_recipes(self):
        """The active recipes that make the items or use them as ingredients."""
        # Odoo archives a template's variants with active_test off, so the domain names the recipes' state itself.
        return (
            self.env[MODEL_RECIPE]
            .sudo()
            .search(
                Domain("active", "=", True)
                & (Domain("solution_item_id", "in", self.ids) | Domain("line_ids.item_id", "in", self.ids))
            )
        )
