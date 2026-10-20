from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import (
    MODEL_PRODUCT_CATEGORY,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_inventory.constants.settings import COSTING_FIFO, COSTING_MOVING_AVERAGE
from odoo.addons.sol_inventory.constants.xml_ids import STOCK_ITEM_CATEGORY
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS


@tagged("post_install", "-at_install")
class TestCosting(StockCase):
    def setUp(self):
        super().setUp()
        self.start = fields.Datetime.now()

    def at(self, minutes):
        """Moves done at distinct times, as the costing orders them by date."""
        return freeze_time(self.start + timedelta(minutes=minutes))

    def use(self, item, quantity):
        return self.env[MODEL_STOCK_MOVE]._take_quants(item, self.central, quantity, reason="Cleaning")

    def set_costing(self, method):
        self.env[MODEL_RES_CONFIG_SETTINGS].create({"costing_method": method}).execute()

    def container_lot(self, name, price):
        lot = self.env[MODEL_STOCK_LOT].create({"name": name, "product_id": self.acid.id})
        container = self.env[MODEL_STOCK_PACKAGE].create({"name": f"{name}-01"})
        self.receive(self.acid, 500, price, location=self.pesticides_store, lot=lot, container=container)
        return container

    def test_under_first_in_first_out_a_use_takes_the_oldest_receipt_price_first(self):
        with self.at(1):
            self.receive(self.gloves, 100, 10)
        with self.at(2):
            self.receive(self.gloves, 100, 20)
        with self.at(3):
            use = self.use(self.gloves, 150)

        self.assertEqual(use.value, -2000)
        self.assertEqual(self.gloves.total_value, 1000)

    def test_under_moving_average_a_receipt_updates_the_average_cost_and_a_use_costs_at_it(self):
        self.set_costing(COSTING_MOVING_AVERAGE)
        with self.at(1):
            self.receive(self.gloves, 100, 10)
        with self.at(2):
            self.receive(self.gloves, 100, 20)
        self.assertEqual(self.gloves.standard_price, 15)

        with self.at(3):
            use = self.use(self.gloves, 150)
        with self.at(4):
            self.receive(self.gloves, 50, 30)

        self.assertEqual(use.value, -2250)
        self.assertEqual(self.gloves.standard_price, 22.5)
        self.assertEqual(self.gloves.total_value, 2250)

    def test_changing_the_costing_method_leaves_the_cost_of_earlier_moves_unchanged(self):
        with self.at(1):
            self.receive(self.gloves, 100, 10)
        with self.at(2):
            self.receive(self.gloves, 100, 20)
        with self.at(3):
            first = self.use(self.gloves, 150)

        with self.at(4):
            self.set_costing(COSTING_MOVING_AVERAGE)
        self.assertEqual(first.value, -2000)
        self.assertEqual(self.gloves.standard_price, 20)
        self.assertEqual(self.gloves.total_value, 1000)

        with self.at(5):
            self.receive(self.gloves, 50, 30)
        with self.at(6):
            second = self.use(self.gloves, 20)
        self.assertEqual(self.gloves.standard_price, 25)
        self.assertEqual(second.value, -500)

        with self.at(7):
            self.set_costing(COSTING_FIFO)
        self.assertEqual(first.value, -2000)
        self.assertEqual(second.value, -500)
        # Under first in, first out the 80 left are the 50 received last at 30 and 30 of the second receipt at 20.
        self.assertEqual(self.gloves.total_value, 2100)

    def test_under_first_in_first_out_a_container_costs_its_lot_price(self):
        with self.at(1):
            self.container_lot("Cheap", 2)
        with self.at(2):
            dear = self.container_lot("Dear", 4)
        with self.at(3):
            use = self.env[MODEL_STOCK_MOVE]._take_containers(self.acid, dear, 100, check_use=False, reason="Rinse")

        self.assertTrue(self.acid.lot_valuated)
        self.assertEqual(use.value, -400)

    def test_under_moving_average_a_container_costs_the_average_of_its_item(self):
        self.set_costing(COSTING_MOVING_AVERAGE)
        with self.at(1):
            self.container_lot("Cheap", 2)
        with self.at(2):
            dear = self.container_lot("Dear", 4)
        with self.at(3):
            use = self.env[MODEL_STOCK_MOVE]._take_containers(self.acid, dear, 100, check_use=False, reason="Rinse")

        self.assertFalse(self.acid.lot_valuated)
        self.assertEqual(use.value, -300)

    def test_every_stock_item_stays_in_the_category_of_the_costing_method(self):
        category = self.env.ref(STOCK_ITEM_CATEGORY)
        self.assertEqual(self.gloves.categ_id, category)
        self.assertEqual(category.property_cost_method, "fifo")

        self.set_costing(COSTING_MOVING_AVERAGE)

        self.assertEqual(category.property_cost_method, "average")
        with self.assertRaises(UserError):
            self.gloves.categ_id = self.env[MODEL_PRODUCT_CATEGORY].create({"name": "Other"})
        with self.assertRaisesRegex(UserError, "refer to it"):
            category.unlink()

    def test_valuing_stock_posts_no_journal_entry(self):
        with self.at(1):
            receipt = self.receive(self.gloves, 100, 10)
        with self.at(2):
            use = self.use(self.gloves, 30)

        self.assertEqual(self.env.ref(STOCK_ITEM_CATEGORY).property_valuation, "periodic")
        self.assertFalse((receipt | use).account_move_id)
        self.assertEqual(receipt.value, 1000)
