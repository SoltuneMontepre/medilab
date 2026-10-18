from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .containers_case import ContainersCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_USE
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
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
        container = self.put_container(self.acid, 40, "Empty", status=CONTAINER_OPENED)

        self.as_tester(container).action_mark_empty()

        move = container.done_line_ids.move_id
        self.assertEqual(container.status, CONTAINER_DEPLETED)
        self.assertEqual(container.quantity, 0)
        self.assertEqual(move.reason, MARKED_EMPTY)
        self.assertFalse(move.automatic)
        self.assertEqual(move.move_kind, MOVE_CONSUMPTION)
        self.assertFalse(move.is_scrap)
