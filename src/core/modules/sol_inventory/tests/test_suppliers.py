from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .catalog_case import CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER, MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_PARTNER


@tagged("post_install", "-at_install")
class TestSuppliers(CatalogCase):
    def test_a_supplier_gets_a_code_and_is_a_vendor_company(self):
        self.assertTrue(self.supplier.code.startswith("NCC."))
        self.assertTrue(self.supplier.partner_id.is_company)
        self.assertEqual(self.supplier.partner_id.supplier_rank, 1)

    def test_a_supplier_sells_an_item_on_one_line(self):
        line = {"partner_id": self.supplier.partner_id.id, "product_id": self.acid.id, "price": 250000}
        self.env[MODEL_SUPPLIER_INFO].create(line)

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_SUPPLIER_INFO].create({**line, "price": 240000})

    def test_the_storekeeper_keeps_suppliers_and_their_contact_details(self):
        self.grant_inventory(self.storekeeper, "supplier.create.all", "supplier.edit.all")
        suppliers = self.env[MODEL_SUPPLIER].with_user(self.storekeeper.user_id)

        supplier = suppliers.create({"name": "Lab Supplies Ltd.", "phone": "028 3800 1234"})
        supplier.email = "sales@labsupplies.example"

        self.assertEqual(supplier.partner_id.email, "sales@labsupplies.example")
        with self.assertRaises(AccessError):
            self.env[MODEL_SUPPLIER].with_user(self.chemist.user_id).create({"name": "Other Supplies"})

    def test_a_typed_supplier_code_must_be_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_SUPPLIER].create({"name": "Copy Chemicals", "code": self.supplier.code})

    def test_a_supplier_names_the_person_the_laboratory_deals_with(self):
        person = self.env[MODEL_RES_PARTNER].create(
            {"name": "Tran Minh Quan", "parent_id": self.supplier.partner_id.id}
        )

        self.supplier.contact_person_id = person

        self.assertEqual(self.supplier.contact_person_id.parent_id, self.supplier.partner_id)
        self.assertFalse(self.supplier.contact_person_id.is_company)

    def test_an_archived_supplier_keeps_its_prices_but_is_no_longer_offered(self):
        line = self.env[MODEL_SUPPLIER_INFO].create(
            {
                "partner_id": self.supplier.partner_id.id,
                "product_id": self.acid.id,
                "product_tmpl_id": self.acid.product_tmpl_id.id,
                "price": 250000,
            }
        )
        self.assertEqual(self.acid._select_seller(quantity=1).get("supplierinfo"), line)

        self.supplier.action_archive()

        self.assertEqual(self.supplier.with_context(active_test=False).supplier_item_ids, line)
        self.assertFalse(self.acid._select_seller(quantity=1))

        self.supplier.action_unarchive()

        self.assertEqual(self.acid._select_seller(quantity=1).get("supplierinfo"), line)

    def test_a_supplier_is_archived_never_deleted(self):
        with self.assertRaises(AccessError):
            self.supplier.with_user(self.env.ref("base.user_admin")).unlink()
