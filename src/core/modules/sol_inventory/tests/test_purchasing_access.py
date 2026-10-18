from odoo.exceptions import AccessError
from odoo.tests import Form, tagged

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_STOCK_LOT
from odoo.addons.sol_laboratory.constants.xml_ids import ADMINISTRATOR_GROUP

ODOO_STOCK_AND_PURCHASE_GROUPS = (
    "stock.group_stock_user",
    "stock.group_stock_manager",
    "purchase.group_purchase_user",
    "purchase.group_purchase_manager",
)


@tagged("post_install", "-at_install")
class TestPurchasingAccess(PurchasingCase):
    def test_the_storekeeper_buys_and_receives_through_permissions_only(self):
        for group in ODOO_STOCK_AND_PURCHASE_GROUPS:
            self.assertFalse(self.buyer.has_group(group), group)
        order = self.sent_order((self.acid, 1000, 1200))
        receipt = order.picking_ids.with_user(self.buyer)
        self.fill(receipt, self.acid, ("Lot200", 1000, 2, self.expiry(), self.certificate()))

        receipt.button_validate()

        self.assertEqual(receipt.state, "done")
        self.assertEqual(len(receipt.container_ids), 2)

    def test_validating_a_receipt_needs_the_receipt_edit_permission(self):
        order = self.sent_order((self.gloves, 10, 50000))
        reader = self.create_person("Vo Van Doc", self.chemistry, "doc.vo")
        self.grant_inventory(reader, "receipt.read.all")
        receipt = order.picking_ids.with_user(reader.user_id)

        with self.assertRaises(AccessError):
            receipt.button_validate()

        self.assertEqual(receipt.state, "assigned")

    def test_a_department_reads_only_the_purchase_orders_it_asked_for(self):
        chemistry_order = self.make_order((self.gloves, 10, 50000), department_id=self.chemistry.id)
        microbiology_order = self.make_order((self.gloves, 5, 50000), department_id=self.microbiology.id)
        self.grant_inventory(self.chemist, "purchase_order.read.own_department")

        orders = (
            self.env[MODEL_PURCHASE_ORDER]
            .with_user(self.chemist.user_id)
            .search([("id", "in", (chemistry_order | microbiology_order).ids)])
        )

        self.assertEqual(orders, chemistry_order)

    def test_lots_are_read_by_everyone_and_edited_with_the_lot_permission(self):
        lot = self.env[MODEL_STOCK_LOT].create({"name": "Lot300", "product_id": self.acid.id})

        self.assertEqual(lot.with_user(self.chemist.user_id).name, "Lot300")
        with self.assertRaises(AccessError):
            lot.with_user(self.chemist.user_id).certificate_id = self.certificate()

        lot.with_user(self.buyer).certificate_id = self.certificate()
        self.assertTrue(lot.certificate_id)

    def test_administrators_configure_odoo_inventory_and_purchase(self):
        administrators = self.env.ref(ADMINISTRATOR_GROUP)

        for group in ("stock.group_stock_manager", "purchase.group_purchase_manager"):
            self.assertIn(self.env.ref(group), administrators.all_implied_ids, group)

    def test_receipts_show_lots_and_locations_to_internal_users(self):
        for group in ("stock.group_production_lot", "stock.group_stock_multi_locations"):
            self.assertTrue(self.chemist.user_id.has_group(group), group)

    def test_a_signer_reads_the_receipts_of_the_orders_they_read(self):
        order = self.sent_order((self.gloves, 10, 50000))

        receipts = order.with_user(self.signer).picking_ids

        self.assertEqual(receipts.mapped("state"), ["assigned"])
        self.assertEqual(receipts.move_ids.product_id, self.gloves)

    def test_everyone_opens_a_received_lot(self):
        receipt = self.make_receipt((self.acid, 1000, 1200))
        self.fill(receipt, self.acid, ("Lot400", 1000, 2, self.expiry(), None))
        receipt.button_validate()
        lot = receipt.container_ids.lot_id

        form = Form(lot.with_user(self.chemist.user_id))

        self.assertEqual(form.name, "Lot400")
        arch = self.env[MODEL_STOCK_LOT].with_user(self.chemist.user_id).get_view(view_type="form")["arch"]
        self.assertNotIn("action_view_po", arch)
        arch = self.env[MODEL_STOCK_LOT].with_user(self.buyer).get_view(view_type="form")["arch"]
        self.assertIn("action_view_po", arch)
