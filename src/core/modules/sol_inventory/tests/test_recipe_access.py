from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .recipe_case import RECIPE_PERMISSIONS, RecipeCase
from odoo.addons.sol_inventory.constants.models import MODEL_RECIPE


@tagged("post_install", "-at_install")
class TestRecipeAccess(RecipeCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.recipe_keeper = cls.create_person("Hoang Thi Mai", cls.chemistry, "mai.hoang")
        cls.grant_inventory(cls.recipe_keeper, *RECIPE_PERMISSIONS)

    def test_the_holder_of_the_recipe_permissions_keeps_recipes(self):
        recipes = self.env[MODEL_RECIPE].with_user(self.recipe_keeper.user_id)

        recipe = recipes.create(
            {
                "solution_item_id": self.rinse.id,
                "yield_quantity": 1000,
                "shelf_life_days": 7,
                "line_ids": [Command.create({"item_id": self.dilute_acid.id, "quantity": 100})],
            }
        )
        recipe.write(
            {
                "shelf_life_days": 14,
                "line_ids": [
                    Command.update(recipe.line_ids.id, {"quantity": 90}),
                    Command.create({"item_id": self.water.id, "quantity": 910}),
                ],
            }
        )
        recipe.line_ids.filtered(lambda line: line.item_id == self.water).unlink()
        recipe.action_archive()
        recipe.action_unarchive()

        self.assertEqual(recipe.shelf_life_days, 14)
        self.assertEqual(recipe.line_ids.quantity, 90)
        self.assertTrue(recipe.active)

        recipe.unlink()

        self.assertFalse(recipe.exists())

    def test_everyone_else_reads_recipes_but_cannot_change_them(self):
        chemist = self.chemist.user_id
        recipe = self.recipe.with_user(chemist)

        self.assertEqual(recipe.line_ids.item_id, self.acid | self.water)
        for action in (
            lambda: (
                self.env[MODEL_RECIPE]
                .with_user(chemist)
                .create(
                    {
                        "solution_item_id": self.rinse.id,
                        "yield_quantity": 1000,
                        "shelf_life_days": 7,
                        "line_ids": [Command.create({"item_id": self.dilute_acid.id, "quantity": 100})],
                    }
                )
            ),
            lambda: recipe.write({"shelf_life_days": 7}),
            lambda: recipe.line_ids[0].write({"quantity": 70}),
            recipe.action_archive,
            recipe.unlink,
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()
