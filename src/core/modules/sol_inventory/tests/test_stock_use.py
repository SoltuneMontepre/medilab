from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT, MODEL_STOCK_QUANT, MODEL_STOCK_USE
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
    CONTAINER_MISSING,
    CONTAINER_OPENED,
    CONTAINER_SEALED,
    MOVE_CONSUMPTION,
    MOVE_WASTE,
)
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_SPILLED
from odoo.addons.sol_inventory.models.stock.stock_package import MARKED_EMPTY


@tagged("post_install", "-at_install")
class TestStockUse(ContainersCase):
    def record(self, container, kind, quantity, reason=None, tags=None):
        return (
            self.env[MODEL_STOCK_USE]
            .with_user(self.tester.user_id)
            .create(
                {
                    "kind": kind,
                    "container_id": container.id,
                    "item_id": container.item_id.id,
                    "lot_id": container.lot_id.id,
                    "quantity": quantity,
                    "reason": reason,
                    "scrap_reason_tag_ids": [Command.set(tags.ids)] if tags else False,
                }
            )
        )

    def test_a_use_needs_a_reason_and_goes_to_production(self):
        container = self.put_container(self.acid, 100, "Use", status=CONTAINER_OPENED)
        wizard = self.record(container, "use", 25)
        with self.assertRaises(UserError):
            wizard.action_confirm()

        wizard.reason = "Calibration"
        wizard.action_confirm()

        move = container.done_line_ids.move_id
        self.assertEqual(container.quantity, 75)
        self.assertEqual(container.status, CONTAINER_OPENED)
        self.assertEqual(move.move_kind, MOVE_CONSUMPTION)
        self.assertEqual(move.reason, "Calibration")
        self.assertEqual(move.reference, "Calibration")
        self.assertFalse(move.automatic)
        self.assertEqual(move.location_dest_id.usage, "production")

    def test_waste_of_a_sealed_container_is_the_whole_bottle(self):
        container = self.put_container(self.acid, 500, "Whole")
        tags = self.env.ref(SCRAP_SPILLED)
        partial = self.record(container, "waste", 100, tags=tags)
        with self.assertRaises(UserError):
            partial.action_confirm()

        self.record(container, "waste", 500, tags=tags).action_confirm()

        move = container.done_line_ids.move_id
        self.assertEqual(container.status, CONTAINER_DISPOSED)
        self.assertEqual(container.quantity, 0)
        self.assertTrue(move.is_scrap)
        self.assertEqual(move.move_kind, MOVE_WASTE)
        self.assertEqual(move.scrap_reason_tag_ids, tags)
        self.assertEqual(container.status, CONTAINER_DISPOSED)
        self.assertNotEqual(container.status, CONTAINER_SEALED)

    def test_part_of_an_opened_container_can_be_wasted(self):
        container = self.put_container(self.acid, 100, "Spill", status=CONTAINER_OPENED)
        wizard = self.record(container, "waste", 40)
        with self.assertRaises(UserError):
            wizard.action_confirm()

        wizard.scrap_reason_tag_ids = self.env.ref(SCRAP_SPILLED)
        wizard.action_confirm()

        self.assertEqual(container.quantity, 60)
        self.assertEqual(container.status, CONTAINER_OPENED)

    def test_marking_empty_uses_what_is_left(self):
        sealed = self.put_container(self.acid, 40, "Full")
        with self.assertRaises(UserError):
            self.as_tester(sealed).action_mark_empty()
        self.assertEqual((sealed.status, sealed.quantity), (CONTAINER_SEALED, 40))

        container = self.put_container(self.acid, 40, "Empty", status=CONTAINER_OPENED)

        self.as_tester(container).action_mark_empty()

        move = container.done_line_ids.move_id
        self.assertEqual(container.status, CONTAINER_DEPLETED)
        self.assertEqual(container.quantity, 0)
        self.assertEqual((move.reason, move.reference), (MARKED_EMPTY, MARKED_EMPTY))
        self.assertFalse(move.automatic)
        self.assertEqual(move.move_kind, MOVE_CONSUMPTION)
        self.assertFalse(move.is_scrap)

    def test_a_scan_fills_the_container_the_item_and_the_quantity(self):
        container = self.put_container(self.acid, 80, "Scan", status=CONTAINER_OPENED)
        wizard = self.env[MODEL_STOCK_USE].with_user(self.tester.user_id).create({"kind": "use"})
        self.assertEqual(wizard.store_ids, self.pesticides_store)

        wizard.container_scan = "   "
        wizard._onchange_container_scan()
        self.assertFalse(wizard.container_id)

        wizard.container_scan = f"  {container.name}  "
        wizard._onchange_container_scan()
        self.assertEqual(wizard.container_id, container)
        self.assertEqual(wizard.item_id, self.acid)
        self.assertEqual(wizard.lot_id, container.lot_id)
        self.assertEqual(wizard.quantity, 80)
        self.assertFalse(wizard.container_scan)

        kept = (
            self.env[MODEL_STOCK_USE]
            .with_user(self.tester.user_id)
            .create({"kind": "use", "container_id": container.id, "quantity": 5})
        )
        kept._onchange_container_id()
        self.assertEqual(kept.quantity, 5)
        kept.quantity = 0
        kept._onchange_container_id()
        self.assertEqual(kept.quantity, 80)

    def test_a_quantity_or_a_lot_is_taken_from_the_store(self):
        self.put_stock(self.gloves, self.pesticides_store, 10)
        use = self.env[MODEL_STOCK_USE].with_user(self.tester.user_id)
        use.create(
            {
                "kind": "use",
                "item_id": self.gloves.id,
                "location_id": self.pesticides_store.id,
                "quantity": 4,
                "reason": "Training",
            }
        ).action_confirm()
        waste = use.create(
            {
                "kind": "waste",
                "item_id": self.gloves.id,
                "location_id": self.pesticides_store.id,
                "quantity": 2,
            }
        )
        with self.assertRaises(UserError):
            waste.action_confirm()
        waste.scrap_reason_tag_ids = self.env.ref(SCRAP_SPILLED)
        waste.action_confirm()
        self.assertEqual(self.held(self.gloves), 4)

        lot = self.env[MODEL_STOCK_LOT].create(
            {"name": "PL-1", "product_id": self.plates.id, "company_id": self.env.company.id}
        )
        self.env[MODEL_STOCK_QUANT]._update_available_quantity(self.plates, self.pesticides_store, 6, lot_id=lot)
        missing_lot = use.create(
            {
                "kind": "use",
                "item_id": self.plates.id,
                "location_id": self.pesticides_store.id,
                "quantity": 2,
                "reason": "Count",
            }
        )
        with self.assertRaises(UserError):
            missing_lot.action_confirm()
        missing_lot.lot_id = lot
        missing_lot.action_confirm()
        self.assertEqual(self.held(self.plates, lot), 4)

        with self.assertRaises(UserError) as short:
            use.create(
                {
                    "kind": "use",
                    "item_id": self.gloves.id,
                    "location_id": self.pesticides_store.id,
                    "quantity": 100,
                    "reason": "Too many",
                }
            ).action_confirm()
        self.assertIn(self.pesticides_store.name, short.exception.args[0])
        self.assertEqual(self.held(self.gloves), 4)

    def held(self, item, lot=None):
        domain = [("product_id", "=", item.id), ("location_id", "=", self.pesticides_store.id)]
        if lot:
            domain.append(("lot_id", "=", lot.id))
        return sum(self.env[MODEL_STOCK_QUANT].search(domain).mapped("quantity"), 0.0)

    def test_recording_is_refused_without_a_container_a_store_or_permission(self):
        use = self.env[MODEL_STOCK_USE].with_user(self.tester.user_id)
        with self.assertRaises(UserError):
            use.create({"kind": "use", "quantity": 1, "reason": "Training"}).action_confirm()

        with self.assertRaises(UserError) as missing:
            use.create({"kind": "use", "item_id": self.acid.id, "quantity": 1, "reason": "Training"}).action_confirm()
        self.assertIn(self.acid.name, missing.exception.args[0])

        container = self.put_container(self.acid, 40, "Other", status=CONTAINER_OPENED)
        wrong = self.record(container, "use", 10, reason="Training")
        wrong.item_id = self.water
        with self.assertRaises(UserError) as held:
            wrong.action_confirm()
        self.assertIn(container.name, held.exception.args[0])

        container.sudo().status = CONTAINER_MISSING
        with self.assertRaises(UserError) as wasted:
            self.record(container, "waste", 40, tags=self.env.ref(SCRAP_SPILLED)).action_confirm()
        self.assertIn("cannot be wasted", wasted.exception.args[0])

        self.put_stock(self.gloves, self.pesticides_store, 5)
        with self.assertRaises(UserError) as store:
            use.create(
                {
                    "kind": "use",
                    "item_id": self.gloves.id,
                    "location_id": self.central.id,
                    "quantity": 1,
                    "reason": "Training",
                }
            ).action_confirm()
        self.assertIn("your stores", store.exception.args[0])

        clerk = self.create_person("Bui Van Ghi", self.chemistry, "ghi.bui")
        clerk.team_id = self.pesticides
        with self.assertRaises(AccessError):
            self.env[MODEL_STOCK_USE].with_user(clerk.user_id).create(
                {
                    "kind": "use",
                    "item_id": self.gloves.id,
                    "location_id": self.pesticides_store.id,
                    "quantity": 1,
                    "reason": "Training",
                }
            ).action_confirm()
