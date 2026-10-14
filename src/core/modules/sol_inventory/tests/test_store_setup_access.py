from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .stores_case import StoresCase
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOCATION
from odoo.addons.sol_inventory.models.stores.stock_location import STORE_FIELDS

LOCATION_PERMISSIONS = ("read", "create", "edit", "archive")


@tagged("post_install", "-at_install")
class TestStoreSetupAccess(StoresCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.storekeeper.permission_ids = [
            Command.link(cls.env.ref(f"sol_inventory.permission_location_{action}_all").id)
            for action in LOCATION_PERMISSIONS
        ]
        cls.administrator = cls.env.ref("base.user_admin")

    def test_the_storekeeper_maintains_locations_inside_a_store(self):
        locations = self.env[MODEL_STOCK_LOCATION].with_user(self.storekeeper.user_id)

        room = locations.create({"name": "Room 101", "location_id": self.central.id, "conditions": "15–25 °C"})
        self.fridge.with_user(self.storekeeper.user_id).conditions = "2–8 °C, locked"

        copy = room.copy()
        self.assertEqual(room.parent_store_id, self.central)
        self.assertEqual(copy.location_id, self.central)
        self.assertEqual(self.fridge.conditions, "2–8 °C, locked")

    def test_only_an_administrator_sets_up_the_stores(self):
        store = self.chemistry_store.with_user(self.storekeeper.user_id)
        for vals in (
            {"is_store": False},
            {"holder_id": self.microbiology.id},
            {"manager_id": self.storekeeper.employee_id.id},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                store.write(vals)
        with self.assertRaises(AccessError):
            self.env[MODEL_STOCK_LOCATION].with_user(self.storekeeper.user_id).with_context(
                default_is_store=True
            ).create({"name": "Microbiology store", "location_id": self.central.id})

        self.chemistry_store.with_user(self.administrator).manager_id = self.storekeeper.employee_id
        self.assertEqual(self.chemistry_store.manager_id, self.storekeeper.employee_id)

    def test_store_fields_are_read_only_for_everyone_else(self):
        described = self.env[MODEL_STOCK_LOCATION].with_user(self.storekeeper.user_id).fields_get(STORE_FIELDS)

        self.assertTrue(all(field["readonly"] for field in described.values()))

    def test_the_stores_screen_offers_new_only_to_administrators(self):
        view = self.env.ref("sol_inventory.view_medilab_store_list")
        for user, create in ((self.storekeeper.user_id, "False"), (self.administrator, None)):
            stores = self.env[MODEL_STOCK_LOCATION].with_user(user)
            root = etree.fromstring(stores.get_view(view.id, "list")["arch"])
            with self.subTest(user=user.login):
                self.assertEqual(root.get("create"), create)
