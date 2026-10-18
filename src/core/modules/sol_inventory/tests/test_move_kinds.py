from odoo.exceptions import UserError
from odoo.tests import tagged

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.stock import MOVE_RECEIPT


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
