from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_ORDERPOINT,
    MODEL_PURCHASE_ORDER,
    MODEL_STOCK_USE,
    MODEL_SUPPLIER,
    MODEL_SUPPLIER_INFO,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE


@tagged("post_install", "-at_install")
class TestBelowMinimum(StockCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.minimum = cls.env[MODEL_ORDERPOINT].create(
            {
                "product_id": cls.gloves.id,
                "location_id": cls.central.id,
                "product_min_qty": 50,
                "product_max_qty": 200,
                "trigger": "manual",
            }
        )
        # Alerts reach the manager in the application.
        cls.storekeeper.user_id.notification_type = "inbox"

    def use(self, quantity):
        self.env[MODEL_STOCK_USE].with_user(self.storekeeper.user_id).create(
            {
                "kind": "use",
                "item_id": self.gloves.id,
                "location_id": self.central.id,
                "quantity": quantity,
                "reason": "Cleaning",
            }
        ).action_confirm()

    def warnings(self):
        return self.env[MODEL_MAIL_MESSAGE].search(
            [("model", "=", MODEL_ORDERPOINT), ("res_id", "=", self.minimum.id), ("notification_key", "!=", False)]
        )

    def test_falling_below_the_minimum_warns_the_store_manager_once(self):
        self.put_stock(self.gloves, self.central, 60)

        self.use(20)
        self.use(5)

        warning = self.warnings()
        self.assertEqual(len(warning), 1)
        self.assertIn(self.storekeeper.user_id.partner_id, warning.notification_ids.res_partner_id)
        self.assertIn("40", warning.body)

    def test_falling_below_again_warns_again(self):
        self.put_stock(self.gloves, self.central, 60)
        self.use(20)
        self.put_stock(self.gloves, self.central, 40)

        self.use(40)

        self.assertEqual(len(self.warnings()), 2)

    def test_a_move_inside_the_store_does_not_warn(self):
        self.put_stock(self.gloves, self.central, 60)

        self.relocate(
            self.storekeeper.user_id,
            item_id=self.gloves.id,
            location_id=self.central.id,
            location_dest_id=self.fridge.id,
            quantity=30,
            reason="Into the fridge",
        )

        self.assertFalse(self.warnings())

    def test_the_minimum_of_a_store_counts_its_own_stock(self):
        self.put_stock(self.gloves, self.central, 60)
        self.put_stock(self.gloves, self.chemistry_store, 500)

        self.assertEqual(self.minimum.qty_on_hand, 60)

    def test_the_suggested_purchase_offers_no_archived_supplier(self):
        archived = self.env[MODEL_SUPPLIER].create({"name": "Old Gloves Co."})
        lines = self.env[MODEL_SUPPLIER_INFO].create(
            [
                {
                    "partner_id": self.supplier.partner_id.id,
                    "product_id": self.gloves.id,
                    "product_tmpl_id": self.gloves.product_tmpl_id.id,
                    "price": 1900,
                },
                {
                    "partner_id": archived.partner_id.id,
                    "product_id": self.gloves.id,
                    "product_tmpl_id": self.gloves.product_tmpl_id.id,
                    "price": 1800,
                },
            ]
        )
        archived.action_archive()

        offered = self.env[MODEL_SUPPLIER_INFO].search([("id", "in", lines.ids), ("supplier_archived", "=", False)])

        self.assertEqual(offered.partner_id, self.supplier.partner_id)

    def test_the_storekeeper_orders_the_suggested_purchase_from_an_active_supplier(self):
        self.grant_inventory(
            self.storekeeper, "purchase_order.create.all", "minimum_quantity.create.all", "minimum_quantity.edit.all"
        )
        archived = self.env[MODEL_SUPPLIER].create({"name": "Old Gloves Co."})
        self.env[MODEL_SUPPLIER_INFO].create(
            [
                {
                    "partner_id": supplier.partner_id.id,
                    "product_id": self.gloves.id,
                    "product_tmpl_id": self.gloves.product_tmpl_id.id,
                    "price": price,
                }
                for supplier, price in ((archived, 1800), (self.supplier, 1900))
            ]
        )
        archived.action_archive()
        # Odoo's buy rule delivers to the warehouse's stock location, which the central store is in a laboratory.
        stock = self.env.ref("stock.stock_location_stock")
        self.put_stock(self.gloves, stock, 30)
        minimum = (
            self.env[MODEL_ORDERPOINT]
            .with_user(self.storekeeper.user_id)
            .create(
                {
                    "product_id": self.gloves.id,
                    "location_id": stock.id,
                    "product_min_qty": 50,
                    "product_max_qty": 200,
                    "trigger": "manual",
                }
            )
        )

        minimum.with_user(self.storekeeper.user_id).action_replenish()

        order = self.env[MODEL_PURCHASE_ORDER].search([("order_line.product_id", "=", self.gloves.id)])
        self.assertEqual(order.state, "draft")
        self.assertEqual(order.partner_id, self.supplier.partner_id)
        self.assertEqual(order.order_line.product_qty, 170)
        self.assertTrue(minimum.exists())
