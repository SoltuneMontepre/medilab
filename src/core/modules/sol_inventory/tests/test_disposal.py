from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
    MODEL_STOCK_USE,
)
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DISPOSED,
    CONTAINER_OPENED,
    LOT_AVAILABLE,
    LOT_DISPOSED,
    MOVE_DISPOSAL,
)
from odoo.addons.sol_inventory.constants.xml_ids import DISPOSAL_ACTION, SCRAP_EXPIRED, SCRAP_SPILLED


@tagged("post_install", "-at_install")
class TestDisposal(StockCase):
    def disposal_list(self, user):
        return self.listed(user, DISPOSAL_ACTION)

    def expired_container(self, lot_name, **kwargs):
        packages = self.env[MODEL_STOCK_PACKAGE]
        return self.put_container(self.acid, 400, lot_name, expiration=packages._at_utc(self.day(-1)), **kwargs)

    def test_an_expired_container_is_listed_for_disposal_and_cannot_be_used(self):
        container = self.expired_container("Old", status=CONTAINER_OPENED)
        fresh = self.put_container(self.acid, 400, "Fresh", status=CONTAINER_OPENED)

        listed = self.disposal_list(self.storekeeper.user_id)

        self.assertIn(container, listed.package_id)
        self.assertNotIn(fresh, listed.package_id)
        use = self.as_tester(self.env[MODEL_STOCK_USE]).create(
            {"kind": "use", "container_id": container.id, "item_id": self.acid.id, "quantity": 10, "reason": "Rinse"}
        )
        with self.assertRaisesRegex(UserError, "usable date"):
            use.action_confirm()

    def test_an_expired_lot_cannot_be_chosen_for_a_use(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        lot = self.env[MODEL_STOCK_LOT].create(
            {"name": "PCA-OLD", "product_id": self.plates.id, "expiration_date": packages._at_utc(self.day(-2))}
        )
        self.env[MODEL_STOCK_QUANT]._update_available_quantity(self.plates, self.pesticides_store, 20, lot_id=lot)

        self.assertIn(lot, self.disposal_list(self.storekeeper.user_id).lot_id)
        use = self.as_tester(self.env[MODEL_STOCK_USE]).create(
            {
                "kind": "use",
                "item_id": self.plates.id,
                "lot_id": lot.id,
                "location_id": self.pesticides_store.id,
                "quantity": 5,
                "reason": "Cleaning",
            }
        )
        with self.assertRaisesRegex(UserError, "can be used"):
            use.action_confirm()

    def test_disposal_moves_what_remains_to_scrap_with_the_reason_expired(self):
        container = self.expired_container("Gone", status=CONTAINER_OPENED)
        quants = self.disposal_list(self.storekeeper.user_id)

        quants.with_user(self.storekeeper.user_id).action_dispose()

        move = self.env[MODEL_STOCK_MOVE].search(
            [("move_kind", "=", MOVE_DISPOSAL), ("move_line_ids.package_id", "=", container.id)]
        )
        self.assertEqual(move.quantity, 400)
        self.assertTrue(move.is_scrap)
        self.assertEqual(move.location_dest_id, self.env.company.scrap_location_id)
        self.assertEqual(move.scrap_reason_tag_ids, self.env.ref(SCRAP_EXPIRED))
        self.assertEqual(container.status, CONTAINER_DISPOSED)
        self.assertEqual(container.lot_id.status, LOT_DISPOSED)

    def test_a_container_past_its_own_usable_date_leaves_its_lot_available(self):
        container = self.put_container(self.acid, 400, "Opened", status=CONTAINER_OPENED)
        container.opened_at = container.opened_at.replace(year=container.opened_at.year - 1)

        self.disposal_list(self.storekeeper.user_id).with_user(self.storekeeper.user_id).action_dispose()

        self.assertEqual(container.status, CONTAINER_DISPOSED)
        self.assertEqual(container.lot_id.status, LOT_AVAILABLE)

    def test_only_expired_stock_is_disposed_of(self):
        self.put_container(self.acid, 400, "Usable", status=CONTAINER_OPENED)
        quants = self.env[MODEL_STOCK_QUANT].search([("product_id", "=", self.acid.id)])

        with self.assertRaisesRegex(UserError, "Only expired stock"):
            quants.with_user(self.storekeeper.user_id).action_dispose()

    def test_disposal_is_for_who_keeps_the_store(self):
        self.expired_container("Kept")
        quants = self.disposal_list(self.storekeeper.user_id)

        with self.assertRaisesRegex(UserError, "store you keep"):
            quants.with_user(self.tester.user_id).action_dispose()
        self.tester.permission_ids = [Command.clear()]
        with self.assertRaises(AccessError):
            quants.with_user(self.tester.user_id).action_dispose()

    def test_expired_stock_is_disposed_of_rather_than_wasted(self):
        container = self.put_container(self.acid, 400, "Waste", status=CONTAINER_OPENED)

        with self.assertRaises(ValueError):
            self.as_tester(self.env[MODEL_STOCK_USE]).create(
                {
                    "kind": "waste",
                    "container_id": container.id,
                    "item_id": self.acid.id,
                    "quantity": 10,
                    "scrap_reason_tag_ids": [Command.set(self.env.ref(SCRAP_EXPIRED).ids)],
                }
            )

    def test_a_reason_a_move_names_cannot_be_deleted(self):
        expired = self.env.ref(SCRAP_EXPIRED)
        spilled = self.env.ref(SCRAP_SPILLED)
        container = self.put_container(self.acid, 400, "Spill", status=CONTAINER_OPENED)
        self.as_tester(self.env[MODEL_STOCK_USE]).create(
            {
                "kind": "waste",
                "container_id": container.id,
                "item_id": self.acid.id,
                "quantity": 10,
                "scrap_reason_tag_ids": [Command.set(spilled.ids)],
            }
        ).action_confirm()

        with self.assertRaisesRegex(UserError, "every disposal"):
            expired.unlink()
        with self.assertRaisesRegex(UserError, "moves name them"):
            spilled.unlink()
