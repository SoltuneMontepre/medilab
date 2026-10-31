from odoo.fields import Command
from odoo.tests import tagged

from .stores_case import StoresCase
from odoo.addons.sol_inventory.constants.models import MODEL_ANALYTIC_ACCOUNT, MODEL_STOCK_LOCATION
from odoo.addons.sol_inventory.constants.xml_ids import COST_CENTRE_PLAN
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestStoreCostCentres(StoresCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.stores = cls.central | cls.chemistry_store | cls.pesticides_store
        cls.chemistry_centre = cls.create_cost_centre("Chemistry", "TEST-HH", cls.chemistry)

    @classmethod
    def create_cost_centre(cls, name, code, department):
        return cls.env[MODEL_ANALYTIC_ACCOUNT].create(
            {"name": name, "code": code, "department_id": department.id, "plan_id": cls.env.ref(COST_CENTRE_PLAN).id}
        )

    def stores_without_cost_centre(self):
        self.env.invalidate_all()
        return self.env[MODEL_STOCK_LOCATION].search(
            [("cost_centre_missing", "=", True), ("id", "in", self.stores.ids)]
        )

    def test_a_store_whose_holder_has_no_cost_centre_is_marked(self):
        self.assertEqual(self.chemistry_store.cost_centre_code, "TEST-HH")
        self.assertEqual(self.stores_without_cost_centre(), self.pesticides_store)
        self.assertFalse(self.central.cost_centre_missing)

        self.create_cost_centre("Pesticide residues", "TEST-HH-TBVTV", self.pesticides)

        self.assertFalse(self.stores_without_cost_centre())

        self.chemistry_centre.action_archive()

        self.assertEqual(self.stores_without_cost_centre(), self.chemistry_store)

    def test_the_stores_screen_shows_the_cost_centre_to_those_who_cannot_open_cost_centres(self):
        self.storekeeper.permission_ids = [
            Command.link(persisted_id(self.env.ref("sol_inventory.permission_location_read_all")))
        ]

        store = self.chemistry_store.with_user(self.storekeeper.user_id)

        self.assertEqual(store.read(["cost_centre_code", "cost_centre_missing"])[0]["cost_centre_code"], "TEST-HH")
