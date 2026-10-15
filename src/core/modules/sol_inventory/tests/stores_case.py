from odoo.fields import Command

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOCATION
from odoo.addons.sol_laboratory.tests.people_case import PeopleCase


class StoresCase(PeopleCase):
    """A central store with a fridge, a Chemistry store and the store of its Pesticide residues team."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        locations = cls.env[MODEL_STOCK_LOCATION]
        # Stores of other data, such as the demo stores, would make a second central store.
        locations.search([("is_store", "=", True)]).is_store = False
        cls.pesticides = cls.create_team("Pesticide residues", cls.chemistry)
        cls.pathogens = cls.create_team("Pathogens", cls.microbiology)
        cls.storekeeper = cls.create_person("Pham Van Kho", cls.chemistry, "kho.pham")
        cls.central = cls.create_store("Central store", cls.env.ref("stock.warehouse0").view_location_id)
        cls.central.manager_id = cls.storekeeper.employee_id
        cls.fridge = locations.create({"name": "Fridge 1", "location_id": cls.central.id, "conditions": "2–8 °C"})
        cls.chemistry_store = cls.create_store("Chemistry store", cls.central, cls.chemistry)
        cls.pesticides_store = cls.create_store("Pesticide residues store", cls.chemistry_store, cls.pesticides)

    @classmethod
    def create_store(cls, name, parent, holder=None):
        return cls.env[MODEL_STOCK_LOCATION].create(
            {"name": name, "location_id": parent.id, "is_store": True, "holder_id": holder.id if holder else False}
        )

    @classmethod
    def grant_inventory(cls, person, *codes):
        """Give the person the Inventory permissions named by their codes, such as stock_item.create.all."""
        person.permission_ids = [
            Command.link(cls.env.ref(f"sol_inventory.permission_{code.replace('.', '_')}").id) for code in codes
        ]
