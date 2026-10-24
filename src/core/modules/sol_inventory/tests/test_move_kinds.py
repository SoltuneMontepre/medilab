from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_MOVE, MODEL_STOCK_QUANT
from odoo.addons.sol_inventory.constants.stock import MOVE_ADJUSTMENT, MOVE_CONSUMPTION, MOVE_RECEIPT


@tagged("post_install", "-at_install")
class TestMoveKinds(PurchasingCase):
    def test_a_receipt_move_is_a_receipt_and_a_done_move_is_never_changed(self):
        receipt = self.make_receipt((self.acid, 1000, 1200))
        self.fill(receipt, self.acid, ("Lot123", 1000, 2, self.expiry(), None))
        receipt.button_validate()

        self.assertEqual(set(receipt.move_ids.mapped("move_kind")), {MOVE_RECEIPT})
        with self.assertRaises(UserError):
            receipt.move_ids.write({"product_uom_qty": 1})
        with self.assertRaises(UserError):
            receipt.move_line_ids.write({"quantity": 1})

    def test_an_inventory_adjustment_is_an_adjustment(self):
        self.put_stock(self.gloves, self.central, 10)
        quant = self.env[MODEL_STOCK_QUANT].search(
            [("product_id", "=", self.gloves.id), ("location_id", "=", self.central.id)]
        )
        quant.with_context(inventory_mode=True).write({"inventory_quantity": 15})
        quant.with_context(inventory_mode=True).action_apply_inventory()

        move = self.env[MODEL_STOCK_MOVE].search(
            [("is_inventory", "=", True), ("product_id", "=", self.gloves.id)], order="id desc", limit=1
        )
        self.assertEqual(move.move_kind, MOVE_ADJUSTMENT)

    def test_the_kind_comes_from_the_move_and_not_from_who_creates_it(self):
        """A move on a receipt is a receipt whatever kind is passed, so recording a use cannot add one to a receipt."""
        tester = self.create_person("Mai Thi Thu", self.chemistry, "thu.mai")
        self.grant_inventory(tester, "move.create.all")
        receipt = self.make_receipt((self.gloves, 10, 50000))
        vals = {
            "product_id": self.gloves.id,
            "product_uom_qty": 1,
            "location_id": receipt.location_id.id,
            "location_dest_id": receipt.location_dest_id.id,
            "picking_id": receipt.id,
            "move_kind": MOVE_CONSUMPTION,
        }

        self.assertEqual(self.env[MODEL_STOCK_MOVE].create(vals).move_kind, MOVE_RECEIPT)
        with self.assertRaises(AccessError):
            self.env[MODEL_STOCK_MOVE].with_user(tester.user_id).create(vals)
