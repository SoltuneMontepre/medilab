from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_MOVE, MODEL_STOCK_QUANT
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED, MOVE_RELOCATION


@tagged("post_install", "-at_install")
class TestRelocation(StockCase):
    def test_a_move_between_the_locations_of_a_store_leaves_its_total_unchanged(self):
        self.put_stock(self.gloves, self.central, 100)

        self.relocate(
            self.storekeeper.user_id,
            item_id=self.gloves.id,
            location_id=self.central.id,
            location_dest_id=self.fridge.id,
            quantity=40,
            reason="Into the fridge",
        )

        move = self.env[MODEL_STOCK_MOVE].search([("reason", "=", "Into the fridge")])
        self.assertEqual(move.move_kind, MOVE_RELOCATION)
        self.assertEqual(move.reference, "Into the fridge")
        self.assertFalse(move.picking_id)
        self.assertEqual(self.held(self.gloves, self.fridge), 40)
        self.assertEqual(self.held(self.gloves, self.central), 100)

    def test_a_container_keeps_its_status_and_usable_date(self):
        container = self.put_container(self.acid, 400, "Bench", status=CONTAINER_OPENED)
        usable_until = container.usable_until

        self.relocate(
            self.storekeeper.user_id, container_id=container.id, location_dest_id=self.bench.id, reason="To the bench"
        )

        self.assertEqual(container.location_id, self.bench)
        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(container.usable_until, usable_until)
        self.assertEqual(container.quantity, 400)

    def test_a_lot_kept_by_lot_moves_its_quantity(self):
        lot = self.env[MODEL_STOCK_LOT].create({"name": "PCA-01", "product_id": self.plates.id})
        self.env[MODEL_STOCK_QUANT]._update_available_quantity(self.plates, self.central, 30, lot_id=lot)

        self.relocate(
            self.storekeeper.user_id,
            item_id=self.plates.id,
            lot_id=lot.id,
            location_id=self.central.id,
            location_dest_id=self.fridge.id,
            quantity=30,
            reason="Plates are kept cold",
        )

        self.assertEqual(self.plates.with_context(location=self.fridge.id, lot_id=lot.id).qty_available, 30)

    def test_a_move_into_another_store_is_refused(self):
        self.put_stock(self.gloves, self.central, 100)

        with self.assertRaisesRegex(UserError, "requisition or a transfer"):
            self.relocate(
                self.storekeeper.user_id,
                item_id=self.gloves.id,
                location_id=self.central.id,
                location_dest_id=self.chemistry_store.id,
                quantity=10,
                reason="Wrong store",
            )
        self.assertEqual(self.held(self.gloves, self.central), 100)

    def test_a_move_needs_a_reason(self):
        self.put_stock(self.gloves, self.central, 100)

        with self.assertRaisesRegex(UserError, "reason"):
            self.relocate(
                self.storekeeper.user_id,
                item_id=self.gloves.id,
                location_id=self.central.id,
                location_dest_id=self.fridge.id,
                quantity=10,
            )

    def test_only_who_keeps_the_store_moves_its_stock(self):
        container = self.put_container(self.acid, 400, "Tester", status=CONTAINER_OPENED)

        with self.assertRaisesRegex(UserError, "store you keep"):
            self.relocate(self.tester.user_id, container_id=container.id, location_dest_id=self.bench.id, reason="x")

    def test_moving_stock_needs_the_move_permission(self):
        clerk = self.create_person("Le Van Kho", self.chemistry, "kho.le")
        self.central.manager_id = clerk.employee_id
        self.put_stock(self.gloves, self.central, 100)

        with self.assertRaises(AccessError):
            self.relocate(
                clerk.user_id,
                item_id=self.gloves.id,
                location_id=self.central.id,
                location_dest_id=self.fridge.id,
                quantity=10,
                reason="x",
            )
