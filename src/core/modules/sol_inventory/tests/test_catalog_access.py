from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools.safe_eval import safe_eval

from .catalog_case import CATALOG_PERMISSIONS, CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT

CATALOG_ACTIONS = (
    "sol_inventory.action_medilab_stock_item",
    "sol_inventory.action_medilab_supplier",
    "sol_inventory.action_medilab_location",
)


@tagged("post_install", "-at_install")
class TestCatalogAccess(CatalogCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant_inventory(cls.storekeeper, *CATALOG_PERMISSIONS)

    def test_the_storekeeper_keeps_items_with_their_minimums_suppliers_and_use(self):
        items = self.env[MODEL_PRODUCT].with_user(self.storekeeper.user_id)

        item = items.create({"name": "Filter paper", "item_kind": "consumable", "item_tracking": "lot"})
        item.write(
            {
                "name": "Filter paper, 90 mm",
                "orderpoint_ids": [
                    Command.create({"location_id": self.central.id, "product_min_qty": 5, "product_max_qty": 20})
                ],
                "supplier_item_ids": [
                    Command.create(
                        {
                            "partner_id": self.supplier.partner_id.id,
                            "product_tmpl_id": item.product_tmpl_id.id,
                            "product_code": "FP-90",
                            "price": 120000,
                        }
                    )
                ],
                "consumption_ids": [Command.create({"method_id": self.method.id, "quantity": 1})],
            }
        )

        self.assertEqual(item.name, "Filter paper, 90 mm")
        self.assertEqual(item.orderpoint_ids.product_min_qty, 5)
        self.assertEqual(item.supplier_item_ids.product_code, "FP-90")
        self.assertEqual(item.consumption_ids.method_id, self.method)

        item.action_archive()

        self.assertFalse(item.active)

    def test_everyone_else_reads_the_catalog_but_cannot_change_it(self):
        chemist = self.chemist.user_id
        items = self.env[MODEL_PRODUCT].with_user(chemist)

        self.assertEqual(self.acid.with_user(chemist).chemical_id, self.nitric_acid)
        for action in (
            lambda: items.create({"name": "Filter paper", "item_kind": "consumable", "item_tracking": "lot"}),
            lambda: self.acid.with_user(chemist).write({"name": "Nitric acid"}),
            self.gloves.with_user(chemist).action_archive,
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()

    def test_the_catalog_screens_open_for_the_storekeeper_and_everyone_else(self):
        # Reading every field a screen shows catches a field whose compute needs rights the user lacks.
        for user in (self.storekeeper.user_id, self.chemist.user_id):
            for xml_id in CATALOG_ACTIONS:
                action = self.env.ref(xml_id)
                records = self.env[action.res_model].with_user(user)
                views = records.get_views(
                    [(view.view_id.id, view.view_mode) for view in action.view_ids]
                    or [(False, "list"), (False, "form")]
                )
                for view_type, view in views["views"].items():
                    names = {node.get("name") for node in etree.fromstring(view["arch"]).iterfind(".//field")}
                    with self.subTest(user=user.login, action=xml_id, view=view_type):
                        records.search(safe_eval(action.domain or "[]"), limit=5).read(
                            sorted(names & set(records._fields))
                        )

    def test_the_storekeeper_cannot_change_products_that_are_not_stock_items(self):
        service = self.env[MODEL_PRODUCT].create({"name": "Lead (Pb) test", "type": "service"})

        with self.assertRaises(AccessError):
            service.with_user(self.storekeeper.user_id).write({"item_kind": "consumable"})
        with self.assertRaises(AccessError):
            service.with_user(self.storekeeper.user_id).write({"default_code": "PB"})
        self.assertFalse(service.item_kind)
