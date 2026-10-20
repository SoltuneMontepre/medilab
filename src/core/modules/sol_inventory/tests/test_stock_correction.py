from odoo.exceptions import UserError
from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_MOVE, MODEL_STOCK_QUANT
from odoo.addons.sol_inventory.constants.stock import CONTAINER_DEPLETED, CONTAINER_OPENED, MOVE_ADJUSTMENT


@tagged("post_install", "-at_install")
class TestStockCorrection(StockCase):
    def move(self, reason):
        return self.env[MODEL_STOCK_MOVE].search([("reason", "=", reason)])

    def test_a_correction_is_an_inventory_adjustment_with_its_reason(self):
        self.put_stock(self.gloves, self.central, 100)

        self.correct(
            self.storekeeper.user_id,
            item_id=self.gloves.id,
            location_id=self.central.id,
            counted_quantity=94,
            reason="Torn boxes thrown away",
        )

        move = self.move("Torn boxes thrown away")
        self.assertEqual(move.move_kind, MOVE_ADJUSTMENT)
        self.assertTrue(move.is_inventory)
        self.assertEqual(move.quantity, 6)
        self.assertEqual(move.reference, "Torn boxes thrown away")
        self.assertEqual(self.held(self.gloves, self.central), 94)

    def test_stock_found_of_a_lot_is_added(self):
        lot = self.env[MODEL_STOCK_LOT].create({"name": "PCA-02", "product_id": self.plates.id})

        self.correct(
            self.storekeeper.user_id,
            item_id=self.plates.id,
            lot_id=lot.id,
            location_id=self.fridge.id,
            counted_quantity=12,
            reason="Found behind the fridge",
        )

        move = self.move("Found behind the fridge")
        self.assertEqual(move.location_dest_id, self.fridge)
        self.assertEqual(move.move_line_ids.lot_id, lot)
        self.assertEqual(self.plates.with_context(location=self.fridge.id, lot_id=lot.id).qty_available, 12)

    def test_a_container_corrected_to_zero_is_depleted(self):
        container = self.put_container(self.acid, 400, "Dry", status=CONTAINER_OPENED)

        self.correct(self.storekeeper.user_id, container_id=container.id, counted_quantity=0, reason="Bottle is dry")

        self.assertEqual(container.status, CONTAINER_DEPLETED)
        self.assertEqual(self.move("Bottle is dry").move_kind, MOVE_ADJUSTMENT)

    def test_stock_counted_in_a_container_that_ran_out_goes_back_into_it(self):
        container = self.put_container(self.acid, 400, "Ran out", status=CONTAINER_OPENED)
        quants = self.env[MODEL_STOCK_QUANT]
        quants._update_available_quantity(
            self.acid, self.pesticides_store, -400, lot_id=container.lot_id, package_id=container
        )
        quants._unlink_zero_quants()

        self.correct(
            self.storekeeper.user_id,
            container_id=container.id,
            location_id=self.pesticides_store.id,
            counted_quantity=150,
            reason="Some left at the bottom",
        )

        self.assertEqual(container.quantity, 150)
        self.assertEqual(container.location_id, self.pesticides_store)

    def test_a_correction_changes_the_quantity(self):
        self.put_stock(self.gloves, self.central, 100)

        with self.assertRaisesRegex(UserError, "already holds"):
            self.correct(
                self.storekeeper.user_id,
                item_id=self.gloves.id,
                location_id=self.central.id,
                counted_quantity=100,
                reason="Counted",
            )

    def test_only_who_keeps_the_store_corrects_its_stock(self):
        container = self.put_container(self.acid, 400, "Other", status=CONTAINER_OPENED)

        with self.assertRaisesRegex(UserError, "store you keep"):
            self.correct(self.tester.user_id, container_id=container.id, counted_quantity=300, reason="Counted")
