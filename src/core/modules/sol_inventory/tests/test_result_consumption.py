from datetime import timedelta
from types import SimpleNamespace

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from odoo.addons.sol_inventory.constants.models import (
    MODEL_METHOD_CONSUMPTION,
    MODEL_PRODUCT,
    MODEL_RESULT_CONTAINER,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_LOT,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_DEPLETED, CONTAINER_OPENED
from odoo.addons.sol_laboratory.constants.models import MODEL_CHEMICAL, MODEL_PARAMETER_METHOD, MODEL_SUBCONTRACTOR
from odoo.addons.sol_laboratory.tests.result_case import ResultCase


@tagged("post_install", "-at_install")
class TestResultConsumption(ResultCase):
    """Usual use is deducted from the store of the person who entered the result."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.tz = "UTC"
        locations = cls.env[MODEL_STOCK_LOCATION]
        locations.search([("is_store", "=", True)]).write({"is_store": False})
        warehouse = cls.env.ref("stock.warehouse0")
        cls.central = locations.create(
            {"name": "Central store", "location_id": warehouse.view_location_id.id, "is_store": True}
        )
        cls.department_store = locations.create(
            {
                "name": "Department store",
                "location_id": cls.central.id,
                "is_store": True,
                "holder_id": cls.tester.department_id.id,
            }
        )
        cls.team = cls.create_team("Pesticide residues", cls.tester.department_id)
        cls.tester.team_id = cls.team
        cls.team_store = locations.create(
            {
                "name": "Pesticide residues store",
                "location_id": cls.department_store.id,
                "is_store": True,
                "holder_id": cls.team.id,
            }
        )
        chemical = cls.env[MODEL_CHEMICAL].create({"code": "TEST-ACN", "name": "Acetonitrile"})
        cls.acetonitrile = cls.env[MODEL_PRODUCT].create(
            {
                "name": "Acetonitrile",
                "item_kind": "chemical",
                "item_tracking": "container",
                "chemical_id": chemical.id,
                "use_expiration_date": True,
                "shelf_life_after_opening_days": 90,
            }
        )
        cls.salt = cls.env[MODEL_PRODUCT].create(
            {
                "name": "Sodium chloride",
                "item_kind": "consumable",
                "item_tracking": "lot",
                "use_expiration_date": True,
            }
        )
        cls.env[MODEL_METHOD_CONSUMPTION].create(
            [
                {"method_id": cls.method.id, "product_id": cls.acetonitrile.id, "quantity": 10},
                {"method_id": cls.method.id, "product_id": cls.salt.id, "quantity": 1},
            ]
        )
        cls.bottle = cls.put_container(cls.acetonitrile, 50, "ACN")
        cls.salt_lot = cls.put_lot(cls.salt, 5, "NaCl", cls.day(30))

    @classmethod
    def put_container(cls, item, quantity, lot_name, expiration=None, location=None):
        packages = cls.env[MODEL_STOCK_PACKAGE]
        lot = cls.env[MODEL_STOCK_LOT].create(
            {
                "name": lot_name,
                "product_id": item.id,
                "company_id": cls.env.company.id,
                "expiration_date": expiration if expiration is not None else packages._at_utc(cls.day(30)),
            }
        )
        container = packages.create(
            {
                "name": f"{lot_name}-01",
                "status": CONTAINER_OPENED,
                "opened_at": fields.Datetime.now(),
                "opened_by_id": cls.tester.user_id.id,
            }
        )
        cls.env[MODEL_STOCK_QUANT]._update_available_quantity(
            item, location or cls.team_store, quantity, lot_id=lot, package_id=container
        )
        return container

    @classmethod
    def put_lot(cls, item, quantity, lot_name, expiration=None, location=None):
        lot = cls.env[MODEL_STOCK_LOT].create(
            {
                "name": lot_name,
                "product_id": item.id,
                "company_id": cls.env.company.id,
                "expiration_date": False if expiration is None else cls.env[MODEL_STOCK_PACKAGE]._at_utc(expiration),
            }
        )
        cls.env[MODEL_STOCK_QUANT]._update_available_quantity(item, location or cls.team_store, quantity, lot_id=lot)
        return lot

    @classmethod
    def day(cls, offset):
        return cls.env[MODEL_STOCK_PACKAGE]._today() + timedelta(days=offset)

    def scan(self, result, *containers):
        lines = self.env[MODEL_RESULT_CONTAINER]
        for sequence, container in enumerate(containers, start=1):
            lines.create({"result_id": result.id, "container_id": container.id, "sequence": sequence})
        return lines

    def test_signing_deducts_the_usual_use_and_links_the_moves(self):
        result = self.enter()
        self.scan(result, self.bottle)

        self.send(result)

        self.assertEqual(self.bottle.quantity, 40)
        self.assertEqual(self.salt_lot.product_qty, 4)
        self.assertEqual(result.move_ids.product_id, self.acetonitrile | self.salt)
        self.assertTrue(all(result.move_ids.mapped("automatic")))
        self.assertEqual(set(result.move_ids.mapped("test_result_id")), {result})
        self.approve(result)
        self.assertEqual(self.bottle.quantity, 40)

    def test_a_lot_with_an_earlier_expiry_is_used_first_and_an_undated_lot_last(self):
        early = self.put_lot(self.salt, 1, "Early", self.day(3))
        self.put_lot(self.salt, 5, "Undated")
        result = self.enter()
        self.scan(result, self.bottle)

        self.send(result)

        salt_move = result.move_ids.filtered(lambda move: move.product_id == self.salt)
        self.assertEqual(salt_move.move_line_ids.lot_id, early)
        self.assertEqual(self.salt_lot.product_qty, 5)

    def test_containers_are_used_in_scan_order_until_each_is_empty(self):
        first = self.put_container(self.acetonitrile, 6, "First")
        second = self.put_container(self.acetonitrile, 8, "Second")
        result = self.enter()
        self.scan(result, first, second)

        self.send(result)

        self.assertEqual(first.quantity, 0)
        self.assertEqual(first.status, CONTAINER_DEPLETED)
        self.assertEqual(second.quantity, 4)
        self.assertEqual(second.status, CONTAINER_OPENED)
        self.assertEqual(self.bottle.quantity, 50)

    def test_a_missing_scan_or_a_shortage_is_refused(self):
        result = self.enter()
        with self.assertRaises(UserError) as missing:
            self.send(result)
        self.assertIn(self.acetonitrile.name, missing.exception.args[0])

        short = self.put_container(self.acetonitrile, 4, "Short")
        self.scan(result, short)
        with self.assertRaises(UserError) as still:
            self.send(result)
        self.assertIn("6", still.exception.args[0])
        self.assertEqual(short.quantity, 4)

    def test_a_container_of_an_unused_item_is_refused(self):
        chemical = self.env[MODEL_CHEMICAL].create({"code": "TEST-ACE", "name": "Acetone"})
        acetone = self.env[MODEL_PRODUCT].create(
            {
                "name": "Acetone",
                "item_kind": "chemical",
                "item_tracking": "container",
                "chemical_id": chemical.id,
                "use_expiration_date": True,
                "shelf_life_after_opening_days": 30,
            }
        )
        bottle = self.put_container(acetone, 20, "Acetone")
        result = self.enter()
        self.scan(result, bottle)

        with self.assertRaises(UserError):
            self.send(result)
        self.assertFalse(result.move_ids)

    def test_an_outsourced_result_does_not_deduct(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"})
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": subcontractor.id,
            }
        )
        result = self.enter()
        self.test.sudo().write({"parameter_method_id": way.id, "status": "outsourced"})

        self.send(result)

        self.assertFalse(result.move_ids)
        self.assertEqual(self.bottle.quantity, 50)

    def test_a_retest_deducts_again_and_a_new_version_does_not(self):
        result = self.enter()
        self.scan(result, self.bottle)
        self.send(result)
        self.as_person(result, self.head).action_reject("The blank was high.")
        retest = self.enter(value=0.009)
        self.scan(retest, self.bottle)
        self.send(retest)

        self.assertEqual(self.bottle.quantity, 30)
        self.assertFalse(retest.replaces_id)
        self.approve(retest)
        version = retest.sudo()._new_version(SimpleNamespace(requested_change="Correct the dilution."))
        self.assertFalse(version.container_line_ids)
        self.send(version)

        self.assertEqual(self.bottle.quantity, 30)
        self.assertFalse(version.move_ids)

    def test_scanned_containers_lock_after_the_first_signature(self):
        result = self.enter()
        self.scan(result, self.bottle)
        self.send(result)
        extra = self.put_container(self.acetonitrile, 10, "Later")

        with self.assertRaises(UserError):
            self.env[MODEL_RESULT_CONTAINER].with_user(self.tester.user_id).create(
                {"result_id": result.id, "container_id": extra.id, "sequence": 2}
            )
        self.assertEqual(result.container_line_ids.container_id, self.bottle)
        with self.assertRaises(UserError):
            result.with_user(self.tester.user_id).write(
                {"container_line_ids": [Command.create({"container_id": extra.id, "sequence": 2})]}
            )
        self.assertEqual(result.container_line_ids.container_id, self.bottle)

    def test_a_scanned_code_adds_the_container_in_order(self):
        result = self.enter()
        result.container_scan = "   "
        result._onchange_container_scan()
        self.assertFalse(result.container_line_ids)

        result.container_scan = f"  {self.bottle.name}  "
        result._onchange_container_scan()
        self.assertEqual(result.container_line_ids.container_id, self.bottle)
        self.assertEqual(result.container_line_ids.sequence, 1)
        self.assertFalse(result.container_scan)

        result.container_scan = self.bottle.name
        with self.assertRaises(UserError) as duplicate:
            result._onchange_container_scan()
        self.assertIn(self.bottle.name, duplicate.exception.args[0])
