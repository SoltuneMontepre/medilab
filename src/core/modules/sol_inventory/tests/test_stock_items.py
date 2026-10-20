from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .catalog_case import CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_METHOD_CONSUMPTION


@tagged("post_install", "-at_install")
class TestStockItems(CatalogCase):
    def test_an_item_without_a_code_gets_one_from_its_sequence(self):
        sequence = self.env.ref("sol_inventory.sequence_stock_item")
        expected = f"{sequence.prefix}{sequence.number_next_actual:0{sequence.padding}d}"

        item = self.create_item("Cotton swabs", "consumable", "lot")

        self.assertEqual(item.default_code, expected)
        self.assertTrue(item.is_storable)

    def test_a_shelf_life_after_opening_is_never_negative(self):
        item = self.create_item("Cotton swabs", "consumable", "lot", shelf_life_after_opening_days=0)

        self.assertEqual(item.shelf_life_after_opening_days, 0)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            item.shelf_life_after_opening_days = -1
            item.flush_recordset()

    def test_a_typed_code_must_be_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_item("Latex gloves", "consumable", "quantity", default_code=self.gloves.default_code)

    def test_a_chemical_item_stocks_exactly_one_laboratory_chemical(self):
        with self.assertRaises(ValidationError):
            self.create_item("Unknown acid", "chemical", "container")
        with self.assertRaises(ValidationError):
            self.create_item("Cotton swabs", "consumable", "lot", chemical_id=self.sodium_chloride.id)

    def test_a_chemical_is_stocked_by_at_most_one_item(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_item("Nitric acid 65%, 1 L", "chemical", "container", chemical_id=self.nitric_acid.id)

    def test_a_chemical_is_tracked_by_container(self):
        with self.assertRaises(ValidationError):
            self.create_item("Sodium chloride, 500 g", "chemical", "lot", chemical_id=self.sodium_chloride.id)

    def test_a_prepared_solution_is_tracked_by_container(self):
        for tracking in ("lot", "quantity"):
            with self.subTest(tracking=tracking), self.assertRaises(ValidationError):
                self.create_item("Nitric acid 5%", "solution", tracking)
        solution = self.create_item("Nitric acid 5%", "solution", "container")

        with self.assertRaises(ValidationError):
            solution.item_tracking = "lot"
        with self.assertRaises(ValidationError):
            solution.product_tmpl_id.tracking = False

    def test_a_prepared_solution_is_never_bought(self):
        solution = self.create_item("Nitric acid 5%", "solution", "container")
        self.assertFalse(solution.purchase_ok)

        with self.assertRaises(ValidationError):
            solution.purchase_ok = True
        # Odoo's own product form writes the template.
        with self.assertRaises(ValidationError):
            solution.product_tmpl_id.purchase_ok = True

    def test_an_item_is_bought_again_once_it_is_no_longer_a_prepared_solution(self):
        buffer = self.create_item("Buffer pH 7", "consumable", "container")
        self.assertTrue(buffer.purchase_ok)

        buffer.item_kind = "solution"
        self.assertFalse(buffer.purchase_ok)

        buffer.item_kind = "consumable"
        self.assertTrue(buffer.purchase_ok)

    def test_an_item_with_stock_on_hand_cannot_be_archived(self):
        self.put_stock(self.gloves, self.fridge, 10)

        with self.assertRaises(UserError) as refusal:
            self.gloves.action_archive()

        self.assertIn(self.fridge.display_name, str(refusal.exception))
        self.assertTrue(self.gloves.active)

    def test_an_item_without_stock_can_be_archived(self):
        self.plates.action_archive()

        self.assertFalse(self.plates.active)

    def test_an_item_an_active_method_uses_per_test_cannot_be_archived(self):
        self.env[MODEL_METHOD_CONSUMPTION].create(
            {"method_id": self.method.id, "product_id": self.plates.id, "quantity": 1}
        )

        with self.assertRaises(UserError) as refusal:
            self.plates.action_archive()

        self.assertIn(self.method.display_name, str(refusal.exception))
        self.assertTrue(self.plates.active)

        self.method.action_archive()
        self.plates.action_archive()

        self.assertFalse(self.plates.active)

    def test_a_stock_item_is_archived_never_deleted(self):
        administrator = self.env.ref("base.user_admin")

        for items in (self.plates, self.plates.with_user(administrator)):
            with self.subTest(user=items.env.user.login), self.assertRaises(UserError):
                items.unlink()
        with self.assertRaises(UserError):
            self.plates.product_tmpl_id.with_user(administrator).unlink()

        self.assertTrue(self.plates.exists())

    def test_changing_the_tracking_of_an_item_with_stock_is_refused(self):
        self.put_stock(self.gloves, self.fridge, 10)

        with self.assertRaises(UserError) as refusal:
            self.gloves.item_tracking = "lot"
        with self.assertRaises(UserError):
            self.gloves.product_tmpl_id.tracking = "lot"

        self.assertIn(self.fridge.display_name, str(refusal.exception))
        self.assertEqual(self.gloves.item_tracking, "quantity")

    def test_the_tracking_of_an_item_without_stock_can_change(self):
        self.plates.item_tracking = "container"

        self.assertEqual((self.plates.tracking, self.plates.track_containers), ("lot", True))

    def test_a_method_uses_an_item_on_one_line(self):
        use = {"method_id": self.method.id, "product_id": self.acid.id, "quantity": 5}
        self.env[MODEL_METHOD_CONSUMPTION].create(use)

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_METHOD_CONSUMPTION].create({**use, "quantity": 2})

    def test_the_use_per_test_is_above_zero(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_METHOD_CONSUMPTION].create(
                {"method_id": self.method.id, "product_id": self.acid.id, "quantity": 0}
            )

    def test_only_items_tracked_by_container_or_lot_keep_an_expiry(self):
        self.plates.use_expiration_date = True

        self.assertTrue(self.plates.use_expiration_date)

        self.plates.item_tracking = "quantity"

        self.assertFalse(self.plates.use_expiration_date)
