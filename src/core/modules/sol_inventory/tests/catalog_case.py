from .stores_case import StoresCase
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_STOCK_QUANT, MODEL_SUPPLIER
from odoo.addons.sol_laboratory.constants.models import MODEL_CHEMICAL, MODEL_TESTING_FIELD, MODEL_TESTING_METHOD

# What the storekeeper is given to keep the catalog.
CATALOG_PERMISSIONS = (
    "stock_item.create.all",
    "stock_item.edit.all",
    "stock_item.archive.all",
    "supplier.create.all",
    "supplier.edit.all",
    "supplier_item.create.all",
    "supplier_item.edit.all",
    "minimum_quantity.create.all",
    "minimum_quantity.edit.all",
    "method_consumption.create.all",
    "method_consumption.edit.all",
)


class CatalogCase(StoresCase):
    """Items tracked by container, lot and quantity, two Laboratory chemicals, a method and a supplier."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nitric_acid, cls.sodium_chloride = cls.env[MODEL_CHEMICAL].create(
            [{"code": "TEST-HC-1", "name": "Nitric acid 65%"}, {"code": "TEST-HC-2", "name": "Sodium chloride"}]
        )
        testing_field = cls.env[MODEL_TESTING_FIELD].create({"code": "TEST-HH", "name": "Chemistry"})
        cls.method = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "TEST 7602:2007", "name": "Lead by AAS", "field_id": testing_field.id}
        )
        cls.acid = cls.create_item("Nitric acid 65%, 500 mL", "chemical", "container", chemical_id=cls.nitric_acid.id)
        cls.plates = cls.create_item("Plate count agar plates", "consumable", "lot")
        cls.gloves = cls.create_item("Nitrile gloves", "consumable", "quantity")
        cls.supplier = cls.env[MODEL_SUPPLIER].create({"name": "Test Chemicals Co."})

    @classmethod
    def create_item(cls, name, kind, tracking, **vals):
        return cls.env[MODEL_PRODUCT].create({"name": name, "item_kind": kind, "item_tracking": tracking, **vals})

    def put_stock(self, item, location, quantity):
        self.env[MODEL_STOCK_QUANT]._update_available_quantity(item, location, quantity)
