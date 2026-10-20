from odoo.exceptions import AccessError
from odoo.tests import tagged

from .stock_case import StockCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOCATION, MODEL_STOCK_PACKAGE, MODEL_STOCK_QUANT
from odoo.addons.sol_inventory.constants.stock import TRANSIT_USAGE
from odoo.addons.sol_inventory.constants.xml_ids import EXPIRING_ACTION, STOCK_ON_HAND_ACTION


@tagged("post_install", "-at_install")
class TestStockOnHand(StockCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.transit = cls.env[MODEL_STOCK_LOCATION].create({"name": "In transit", "usage": TRANSIT_USAGE})

    def on_hand(self, user):
        return self.listed(user, STOCK_ON_HAND_ACTION)

    def test_the_storekeeper_sees_their_store_and_every_store_under_it(self):
        self.put_stock(self.gloves, self.central, 100)
        self.put_stock(self.gloves, self.pesticides_store, 20)
        self.put_stock(self.gloves, self.transit, 5)

        seen = self.on_hand(self.storekeeper.user_id)

        self.assertEqual(seen.location_id, self.central | self.pesticides_store | self.transit)

    def test_stock_in_transit_counts_in_no_store(self):
        self.put_stock(self.gloves, self.transit, 5)

        self.assertEqual(self.held(self.gloves, self.central), 0)
        self.assertEqual(self.held(self.gloves, self.chemistry_store), 0)

    def test_a_team_member_sees_the_stock_of_their_team_store(self):
        self.grant_inventory(self.tester, "stock.read.all")
        self.put_stock(self.gloves, self.central, 100)
        self.put_stock(self.gloves, self.pesticides_store, 20)

        seen = self.on_hand(self.tester.user_id)

        self.assertEqual(seen.location_id, self.pesticides_store)

    def test_the_value_is_shown_with_the_stock_permission(self):
        self.receive(self.gloves, 100, 10)
        quant = self.env[MODEL_STOCK_QUANT].search(
            [("product_id", "=", self.gloves.id), ("location_id", "=", self.central.id)]
        )

        self.assertEqual(quant.with_user(self.storekeeper.user_id).value, 1000)
        with self.assertRaises(AccessError):
            quant.with_user(self.tester.user_id).read(["value"])

    def test_the_expiring_soon_screen_lists_stock_within_the_warning(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        soon = self.put_container(self.acid, 400, "Soon", expiration=packages._at_utc(self.day(10)))
        later = self.put_container(self.acid, 400, "Later", expiration=packages._at_utc(self.day(90)))

        listed = self.listed(self.storekeeper.user_id, EXPIRING_ACTION).package_id

        self.assertIn(soon, listed)
        self.assertNotIn(later, listed)
