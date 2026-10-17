from lxml import etree

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_LOT,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_PICKING,
    MODEL_STOCK_QUANT,
    MODEL_SUPPLIER_INFO,
)


@tagged("post_install", "-at_install")
class TestReceipts(PurchasingCase):
    def test_receiving_part_of_an_order_sets_it_partially_received_and_the_rest_received(self):
        order = self.sent_order((self.gloves, 10, 50000))
        receipt = order.picking_ids.with_user(self.buyer)
        receipt.move_ids.quantity = 4

        result = receipt.button_validate()

        self.assertIs(result, True)
        self.assertEqual(order.receipt_status, "partial")
        self.assertEqual(order.order_line.qty_received, 4)
        backorder = order.picking_ids.filtered(lambda picking: picking.state != "done").with_user(self.buyer)
        self.assertEqual(backorder.move_ids.product_uom_qty, 6)

        backorder.button_validate()

        self.assertEqual(order.receipt_status, "full")
        self.assertEqual(order.order_line.qty_received, 10)

    def test_a_partial_receipt_checks_and_puts_in_containers_only_what_arrived(self):
        salt = self.create_item(
            "Sodium chloride, 1 kg",
            "chemical",
            "container",
            chemical_id=self.sodium_chloride.id,
            use_expiration_date=True,
        )
        receipt = self.make_receipt((self.acid, 1000, 1200), (salt, 1000, 380))
        self.fill(receipt, self.acid, ("Lot123", 1000, 2, self.expiry(), None))
        receipt.move_ids.filtered(lambda move: move.product_id == salt).move_line_ids.write(
            {"lot_name": "Lot900", "container_count": 2}
        )

        receipt.button_validate()

        self.assertEqual(receipt.state, "done")
        self.assertEqual(receipt.container_ids.sorted("name").mapped("name"), ["Lot123-01", "Lot123-02"])
        self.assertFalse(self.env[MODEL_STOCK_PACKAGE].search([("name", "=like", "Lot900-%")]))
        backorder = receipt.backorder_ids
        self.assertEqual(backorder.move_ids.product_id, salt)
        self.assertFalse(backorder.move_line_ids.result_package_id)

    def test_a_receipt_against_an_order_brings_in_only_the_items_the_order_lists(self):
        cotton = self.create_item("Cotton wool", "consumable", "quantity")
        order = self.sent_order((self.gloves, 10, 50000))
        receipt = order.picking_ids.with_user(self.buyer)
        receipt.move_ids.write({"quantity": 10, "picked": True})
        receipt.write(
            {
                "move_ids": [
                    Command.create(
                        {
                            "product_id": cotton.id,
                            "product_uom_qty": 5,
                            "quantity": 5,
                            "picked": True,
                            "location_id": receipt.location_id.id,
                            "location_dest_id": receipt.location_dest_id.id,
                        }
                    )
                ]
            }
        )

        with self.assertRaisesRegex(UserError, "Cotton wool"):
            receipt.button_validate()

        self.assertEqual(order.order_line.product_id, self.gloves)

    def test_receiving_a_chemical_creates_its_lot_with_the_printed_expiry_and_attaches_the_certificate(self):
        order = self.sent_order((self.acid, 2500, 1200))
        receipt = order.picking_ids.with_user(self.buyer)
        certificate = self.certificate()
        self.fill(receipt, self.acid, ("Lot123", 2500, 5, self.expiry(), certificate))

        receipt.button_validate()

        lot = self.env[MODEL_STOCK_LOT].search([("product_id", "=", self.acid.id), ("name", "=", "Lot123")])
        self.assertEqual(lot.expiration_date, self.expiry())
        self.assertEqual(lot.status, "available")
        self.assertEqual(lot.certificate_id, certificate)
        self.assertEqual((certificate.res_model, certificate.res_id), ("stock.lot", lot.id))

    def test_receiving_five_bottles_of_a_lot_creates_five_sealed_containers(self):
        receipt = self.make_receipt((self.acid, 2500, 1200))
        self.fill(receipt, self.acid, ("Lot123", 2500, 5, self.expiry(), None))

        receipt.button_validate()

        containers = receipt.container_ids.sorted("name")
        self.assertEqual(containers.mapped("name"), [f"Lot123-0{number}" for number in range(1, 6)])
        self.assertEqual(set(containers.mapped("status")), {"sealed"})
        self.assertEqual(containers.mapped("quantity"), [500.0] * 5)
        self.assertEqual(set(containers.mapped("usable_until")), {self.expiry().date()})
        self.assertEqual(containers.lot_id.name, "Lot123")
        self.assertEqual(containers.location_id, self.central)

    def test_a_later_receipt_of_a_lot_numbers_its_containers_on(self):
        for count in (5, 2):
            receipt = self.make_receipt((self.acid, 500 * count, 1200))
            self.fill(receipt, self.acid, ("Lot123", 500 * count, count, self.expiry(), None))
            receipt.button_validate()

        self.assertEqual(receipt.container_ids.sorted("name").mapped("name"), ["Lot123-06", "Lot123-07"])

    def test_bottles_share_the_quantity_of_their_line(self):
        receipt = self.make_receipt((self.acid, 1000, 1200))
        self.fill(receipt, self.acid, ("Lot124", 1000, 3, self.expiry(), None))

        receipt.button_validate()

        quantities = receipt.container_ids.sorted("name").mapped("quantity")
        self.assertEqual(len(quantities), 3)
        self.assertAlmostEqual(sum(quantities), 1000)
        self.assertAlmostEqual(max(quantities) - min(quantities), 0, delta=0.02)

    def test_a_lot_of_an_item_with_an_expiry_date_needs_the_printed_expiry(self):
        receipt = self.make_receipt((self.acid, 500, 1200))
        self.fill(receipt, self.acid, ("Lot125", 500, 1, False, None))

        with self.assertRaises(UserError):
            receipt.button_validate()

        self.assertNotEqual(receipt.state, "done")

    def test_goods_can_be_received_only_into_a_location_of_the_central_store(self):
        with self.assertRaises(ValidationError):
            self.make_receipt((self.gloves, 10, 50000), location=self.chemistry_store)

        receipt = self.make_receipt((self.gloves, 10, 50000), location=self.fridge)
        with self.assertRaises(ValidationError):
            receipt.move_ids.move_line_ids.location_dest_id = self.chemistry_store

    def test_goods_are_received_without_a_purchase_order_at_their_price(self):
        receipt = self.make_receipt((self.gloves, 100, 2500))
        receipt.move_ids.quantity = 100

        receipt.button_validate()

        self.assertEqual(receipt.state, "done")
        self.assertEqual(receipt.move_ids.price_unit, 2500)
        quant = self.env[MODEL_STOCK_QUANT].search(
            [("product_id", "=", self.gloves.id), ("location_id", "=", self.central.id)]
        )
        self.assertEqual(quant.quantity, 100)

    def test_done_moves_are_never_changed(self):
        receipt = self.make_receipt((self.gloves, 10, 50000))
        receipt.move_ids.quantity = 10
        receipt.button_validate()

        with self.assertRaises(UserError):
            receipt.sudo().move_ids.move_line_ids.quantity = 8
        with self.assertRaises(UserError):
            receipt.sudo().action_toggle_is_locked()

    def test_a_location_that_received_goods_is_archived_once_its_stock_is_gone(self):
        shelf = self.env[MODEL_STOCK_LOCATION].create({"name": "Shelf 3", "location_id": self.central.id})
        receipt = self.make_receipt((self.gloves, 10, 50000), location=shelf)
        receipt.button_validate()

        with self.assertRaises(UserError):
            shelf.action_archive()

        self.put_stock(self.gloves, shelf, -10)
        shelf.action_archive()
        self.assertFalse(shelf.active)

    def test_a_received_lot_and_its_containers_are_not_deleted(self):
        receipt = self.make_receipt((self.acid, 1000, 1200))
        self.fill(receipt, self.acid, ("Lot126", 1000, 2, self.expiry(), None))
        receipt.button_validate()

        with self.assertRaises(UserError):
            receipt.container_ids.lot_id.unlink()
        with self.assertRaises(UserError):
            receipt.container_ids[0].unlink()

    def test_a_quantity_too_small_for_its_bottles_is_refused(self):
        receipt = self.make_receipt((self.acid, 0.03, 1200))
        self.fill(receipt, self.acid, ("Lot127", 0.03, 4, self.expiry(), None))

        with self.assertRaises(UserError):
            receipt.button_validate()

    def test_a_receipt_keeps_what_each_item_cost_as_its_supplier_last_price(self):
        line = self.env[MODEL_SUPPLIER_INFO].create(
            {"partner_id": self.vendor.id, "product_id": self.gloves.id, "price": 2000}
        )
        receipt = self.make_receipt((self.gloves, 100, 2500), (self.plates, 20, 15000))
        receipt.move_ids.filtered(lambda move: move.product_id == self.gloves).write({"quantity": 100, "picked": True})
        self.fill(receipt, self.plates, ("Lot500", 20, 1, self.expiry(), None))
        receipt.button_validate()

        self.assertEqual(line.price, 2500)
        plates_line = self.env[MODEL_SUPPLIER_INFO].search(
            [("partner_id", "=", self.vendor.id), ("product_id", "=", self.plates.id)]
        )
        self.assertEqual(plates_line.price, 15000)

    def test_an_item_received_without_a_price_keeps_its_supplier_last_price(self):
        line = self.env[MODEL_SUPPLIER_INFO].create(
            {"partner_id": self.vendor.id, "product_id": self.gloves.id, "price": 2000}
        )
        receipt = self.make_receipt((self.gloves, 100, 0))
        receipt.move_ids.quantity = 100

        receipt.button_validate()

        self.assertEqual(receipt.state, "done")
        self.assertEqual(line.price, 2000)

    def test_a_receipt_offers_no_return_to_the_supplier(self):
        root = etree.fromstring(self.env[MODEL_STOCK_PICKING].get_view(view_type="form")["arch"])
        invisible = next(
            button.get("invisible") for button in root.iter("button") if button.get("name") == "action_return"
        )

        self.assertTrue(str(invisible).endswith(" or (picking_type_code == 'incoming')"), invisible)
