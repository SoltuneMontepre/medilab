from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .recipe_case import RecipeCase
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_RECIPE, MODEL_RECIPE_LINE


@tagged("post_install", "-at_install")
class TestRecipes(RecipeCase):
    def test_a_recipe_without_a_code_gets_one_from_its_sequence(self):
        sequence = self.env.ref("sol_inventory.sequence_recipe")
        expected = f"{sequence.prefix}{sequence.number_next_actual:0{sequence.padding}d}"

        recipe = self.create_recipe(self.rinse, {self.dilute_acid: 100, self.water: 900})

        self.assertEqual(recipe.code, expected)
        self.assertEqual(recipe.display_name, f"{expected} – Nitric acid 0.5%")
        self.assertEqual(self.env[MODEL_RECIPE].name_search("Nitric acid 0.5")[0][0], recipe.id)

    def test_a_recipe_without_a_shelf_life_cannot_be_saved(self):
        for shelf_life in (0, False):
            with self.subTest(shelf_life=shelf_life):
                with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
                    self.create_recipe(self.rinse, {self.water: 1000}, shelf_life_days=shelf_life)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.recipe.shelf_life_days = 0
            self.recipe.flush_recordset()

    def test_a_recipe_without_an_ingredient_cannot_be_saved(self):
        with self.assertRaises(ValidationError):
            self.create_recipe(self.rinse, {})
        with self.assertRaises(ValidationError):
            self.recipe.line_ids = [Command.clear()]
        with self.assertRaises(ValidationError):
            self.recipe.line_ids.unlink()
        self.assertEqual(len(self.recipe.line_ids), 2)

    def test_moving_the_last_ingredient_to_another_recipe_is_refused(self):
        recipe = self.create_recipe(self.rinse, {self.dilute_acid: 100})
        line = recipe.line_ids

        with self.assertRaises(ValidationError):
            line.write({"recipe_id": self.recipe.id, "item_id": self.water.id})
        with self.assertRaises(ValidationError):
            self.recipe.line_ids = [Command.link(line.id)]

    def test_an_ingredient_can_be_removed_or_replaced_while_one_is_left(self):
        recipe = self.create_recipe(self.rinse, {self.dilute_acid: 100})

        recipe.line_ids = [
            Command.delete(recipe.line_ids.id),
            Command.create({"item_id": self.water.id, "quantity": 1}),
        ]
        self.recipe.line_ids.filtered(lambda line: line.item_id == self.water).unlink()

        self.assertEqual(recipe.line_ids.item_id, self.water)
        self.assertEqual(self.recipe.line_ids.item_id, self.acid)

    def test_a_recipe_cannot_use_its_own_solution(self):
        with self.assertRaises(ValidationError):
            self.create_recipe(self.rinse, {self.rinse: 100, self.water: 900})
        with self.assertRaises(ValidationError):
            self.recipe.line_ids = [Command.create({"item_id": self.dilute_acid.id, "quantity": 10})]
        with self.assertRaises(ValidationError):
            self.env[MODEL_RECIPE_LINE].create(
                {"recipe_id": self.recipe.id, "item_id": self.dilute_acid.id, "quantity": 10}
            )
        buffer = self.create_item("Ammonium buffer", "solution", "container")
        recipe = self.create_recipe(self.rinse, {buffer: 10, self.water: 990})
        with self.assertRaises(ValidationError):
            recipe.solution_item_id = buffer

    def test_a_recipe_cannot_use_a_solution_prepared_from_its_own(self):
        self.create_recipe(self.rinse, {self.dilute_acid: 100, self.water: 900})
        trace = self.create_item("Nitric acid 0.05%", "solution", "container")
        self.create_recipe(trace, {self.rinse: 100, self.water: 900})

        for ingredient in (self.rinse, trace):
            with self.subTest(ingredient=ingredient.name), self.assertRaises(ValidationError):
                self.recipe.line_ids = [Command.create({"item_id": ingredient.id, "quantity": 10})]

    def test_another_recipe_s_solution_or_one_without_a_recipe_can_be_an_ingredient(self):
        buffer = self.create_item("Ammonium buffer", "solution", "container")

        recipe = self.create_recipe(self.rinse, {self.dilute_acid: 100, buffer: 10, self.water: 890})

        self.assertEqual(recipe.line_ids.item_id, self.dilute_acid | buffer | self.water)

    def test_an_ingredient_is_tracked_by_container(self):
        service = self.env[MODEL_PRODUCT].create({"name": "Lead (Pb) test", "type": "service"})
        for item in (self.plates, self.gloves, service):
            with self.subTest(item=item.name), self.assertRaises(ValidationError):
                self.create_recipe(self.rinse, {item: 1, self.water: 999})

    def test_a_recipe_makes_a_prepared_solution(self):
        with self.assertRaises(ValidationError):
            self.create_recipe(self.water, {self.acid: 10})

    def test_an_archived_item_cannot_be_made_or_used(self):
        cuvette = self.create_item("Quartz cuvette rinse", "consumable", "container", active=False)
        old_solution = self.create_item("Nitric acid 2%", "solution", "container", active=False)

        with self.assertRaises(ValidationError):
            self.create_recipe(self.rinse, {cuvette: 1, self.water: 999})
        with self.assertRaises(ValidationError):
            self.create_recipe(old_solution, {self.acid: 30, self.water: 970})

    def test_an_archived_recipe_cannot_be_restored_with_an_archived_item(self):
        self.recipe.action_archive()
        self.water.action_archive()

        with self.assertRaises(ValidationError):
            self.recipe.action_unarchive()

    def test_an_item_an_active_recipe_makes_or_uses_cannot_be_archived(self):
        for item in (self.acid, self.dilute_acid):
            with self.subTest(item=item.name), self.assertRaises(UserError) as refusal:
                item.action_archive()
            self.assertIn(self.recipe.display_name, str(refusal.exception))

        self.recipe.action_archive()
        (self.acid | self.dilute_acid).action_archive()

        self.assertFalse(self.acid.active or self.dilute_acid.active)

    def test_an_ingredient_or_solution_keeps_what_the_recipe_needs(self):
        cuvette = self.create_item("Quartz cuvette rinse", "consumable", "container")
        self.create_recipe(self.rinse, {cuvette: 1, self.water: 999})

        with self.assertRaises(ValidationError):
            cuvette.item_tracking = "lot"
        with self.assertRaises(ValidationError):
            cuvette.product_tmpl_id.tracking = False
        with self.assertRaises(ValidationError):
            self.dilute_acid.item_kind = "consumable"

    def test_a_prepared_solution_is_made_by_one_recipe(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_recipe(self.dilute_acid, {self.acid: 50, self.water: 950})

    def test_a_recipe_uses_an_item_on_one_line(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.recipe.line_ids = [Command.create({"item_id": self.water.id, "quantity": 10})]
            self.recipe.flush_recordset()

    def test_the_yield_and_amounts_are_above_zero(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_recipe(self.rinse, {self.water: 1000}, yield_quantity=0)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_recipe(self.rinse, {self.dilute_acid: 0, self.water: 1000})

    def test_deleting_a_recipe_deletes_its_ingredients(self):
        lines = self.recipe.line_ids

        self.recipe.unlink()

        self.assertFalse(lines.exists())
