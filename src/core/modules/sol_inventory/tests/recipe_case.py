from odoo.fields import Command

from .catalog_case import CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_RECIPE
from odoo.addons.sol_laboratory.constants.models import MODEL_CHEMICAL

# What the administrator is given to keep the recipes.
RECIPE_PERMISSIONS = (
    "recipe.create.all",
    "recipe.edit.all",
    "recipe.archive.all",
    "recipe.delete.all",
    "recipe_line.create.all",
    "recipe_line.edit.all",
    "recipe_line.delete.all",
)


class RecipeCase(CatalogCase):
    """Water, two prepared solutions and the recipe of 5 % nitric acid from 65 % nitric acid and water."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        water = cls.env[MODEL_CHEMICAL].create({"code": "TEST-HC-3", "name": "Distilled water"})
        cls.water = cls.create_item("Distilled water", "chemical", "container", chemical_id=water.id)
        cls.dilute_acid = cls.create_item("Nitric acid 5%", "solution", "container")
        cls.rinse = cls.create_item("Nitric acid 0.5%", "solution", "container")
        cls.recipe = cls.create_recipe(cls.dilute_acid, {cls.acid: 77, cls.water: 923})

    @classmethod
    def create_recipe(cls, solution, ingredients, **vals):
        """Create the recipe of the solution from the amount of each ingredient item."""
        return cls.env[MODEL_RECIPE].create(
            {
                "solution_item_id": solution.id,
                "yield_quantity": 1000,
                "shelf_life_days": 14,
                "line_ids": [
                    Command.create({"item_id": item.id, "quantity": quantity}) for item, quantity in ingredients.items()
                ],
                **vals,
            }
        )
