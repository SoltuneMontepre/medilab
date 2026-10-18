from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command

from odoo.addons.sol_demo.demo_results import _receive
from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_RESULT_CONTAINER,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
    MODEL_STOCK_USE,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_SEALED, LOT_EXPIRED
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_SPILLED
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST, MODEL_TEST_RESULT

MARKER = "sol_demo.demo_preparation_sulfuric_acid_005m"
TESTER = "sol_demo.demo_res_users_tester"
TESTER_ROLE = "sol_demo.demo_role_tester"
STOREKEEPER_ROLE = "sol_demo.demo_role_storekeeper"
STORE = "sol_demo.demo_stock_location_pesticide_residues_store"
ACETONITRILE_LOT = "ACN-2601"
EXPIRED_LOT = "ACN-2501"
# A sealed bottle of the expired lot, and four bottles of one acetonitrile lot: two sealed, one opened, one empty.
BOTTLE = 1000


# Chai/Lọ
class StockPackage(models.Model):
    _inherit = MODEL_STOCK_PACKAGE

    @api.model
    def _seed_container_demo(self):
        """Opened, sealed, empty and expired containers in the pesticide residues store, one preparation, one signed
        result and one spill. Safe to run again. Roles are linked on every update, because a role is not rewritten."""
        self._grant_demo_roles()
        if self.env.ref(MARKER, raise_if_not_found=False):
            return
        tester = self.env.ref(TESTER)
        store = self.env.ref(STORE)
        item = {
            name: self.env.ref(f"sol_demo.demo_product_product_{name}")
            for name in (
                "acetonitrile",
                "sodium_chloride",
                "sulfuric_acid",
                "distilled_water",
                "sulfuric_acid_005m",
            )
        }
        # Opening dates the usable date from this. The shipped item leaves it at 0.
        item["sodium_chloride"].shelf_life_after_opening_days = 180
        item["sulfuric_acid"].standard_price = 2
        item["distilled_water"].standard_price = 1

        acetonitrile = item["acetonitrile"]
        lot = _lot(self.env, acetonitrile, ACETONITRILE_LOT, 365)
        sealed = [_container(self.env, lot, number, BOTTLE, store) for number in (1, 2)]
        opened = _container(self.env, lot, 3, BOTTLE, store)
        emptied = _container(self.env, lot, 4, BOTTLE, store)
        opened.with_user(tester).action_open()
        emptied.with_user(tester).action_mark_empty()
        expired_lot = _lot(self.env, acetonitrile, EXPIRED_LOT, -1)
        expired_lot.status = LOT_EXPIRED
        expired = _container(self.env, expired_lot, 1, BOTTLE, store)

        salt = _open(self.env, tester, item["sodium_chloride"], "NaCl-2601", 500, store)
        acid = _open(self.env, tester, item["sulfuric_acid"], "H2SO4-2601", 100, store)
        water = _open(self.env, tester, item["distilled_water"], "H2O-2601", 2000, store)
        recipe = self.env.ref("sol_demo.demo_recipe_sulfuric_acid_005m")
        preparation, solution = (
            self.env[MODEL_PREPARATION]
            .with_user(tester)
            .prepare(
                recipe,
                store,
                [
                    {"item": item["sulfuric_acid"], "quantity": 2.8, "containers": acid},
                    {"item": item["distilled_water"], "quantity": 997.2, "containers": water},
                ],
                recipe.yield_quantity,
                self.env["stock.scrap.reason.tag"],
            )
        )
        result = _signed_result(self.env, tester, opened, salt)
        spill = _spill(self.env, tester, opened)

        named = (
            ("demo_stock_lot_acetonitrile", lot),
            ("demo_stock_lot_acetonitrile_expired", expired_lot),
            ("demo_stock_lot_sodium_chloride", salt.lot_id),
            ("demo_stock_lot_sulfuric_acid", acid.lot_id),
            ("demo_stock_lot_distilled_water", water.lot_id),
            ("demo_stock_lot_sulfuric_acid_005m", solution.lot_id),
            ("demo_stock_package_acetonitrile_sealed", sealed[0]),
            ("demo_stock_package_acetonitrile_sealed_2", sealed[1]),
            ("demo_stock_package_acetonitrile_opened", opened),
            ("demo_stock_package_acetonitrile_depleted", emptied),
            ("demo_stock_package_acetonitrile_expired", expired),
            ("demo_stock_package_sodium_chloride", salt),
            ("demo_stock_package_sulfuric_acid", acid),
            ("demo_stock_package_distilled_water", water),
            ("demo_stock_package_sulfuric_acid_005m", solution),
            ("demo_preparation_sulfuric_acid_005m", preparation),
            ("demo_test_request_chlorpyrifos", result.sample_test_id.sample_id.request_id),
            ("demo_test_result_chlorpyrifos", result),
            ("demo_stock_move_spilled", spill),
        )
        self.env["ir.model.data"]._update_xmlids(
            [{"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True} for name, record in named]
        )

    def _grant_demo_roles(self):
        """The tester opens, prepares and records use. The storekeeper reads every move."""
        tester = self.env.ref(TESTER_ROLE)
        storekeeper = self.env.ref(STOREKEEPER_ROLE)
        tester_permissions = self.env["medilab.permission"].browse()
        for code in ("container_edit_all", "preparation_create_all", "move_create_all"):
            tester_permissions |= self.env.ref(f"sol_inventory.permission_{code}")
        tester.write({"permission_ids": [Command.link(permission.id) for permission in tester_permissions]})
        storekeeper.write({"permission_ids": [Command.link(self.env.ref("sol_inventory.permission_move_read_all").id)]})


def _lot(env, item, name, days):
    packages = env[MODEL_STOCK_PACKAGE]
    return env[MODEL_STOCK_LOT].create(
        {
            "name": name,
            "product_id": item.id,
            "company_id": env.company.id,
            "expiration_date": packages._at_utc(packages._today() + timedelta(days=days)),
        }
    )


def _container(env, lot, number, quantity, location, status=CONTAINER_SEALED):
    container = env[MODEL_STOCK_PACKAGE].create({"name": f"{lot.name}-{number:02d}", "status": status})
    env[MODEL_STOCK_QUANT]._update_available_quantity(
        lot.product_id, location, quantity, lot_id=lot, package_id=container
    )
    return container


def _open(env, tester, item, lot_name, quantity, location):
    container = _container(env, _lot(env, item, lot_name, 365), 1, quantity, location)
    container.with_user(tester).action_open()
    return container


def _signed_result(env, tester, *containers):
    """An in-house chlorpyrifos result, signed by the tester, which deducts the method's usual use."""
    parameter = env.ref("sol_demo.demo_test_parameter_chlorpyrifos")
    request = env[MODEL_TEST_REQUEST].create(
        {
            "customer_id": env.ref("sol_demo.demo_customer_green_farm").id,
            "expected_date": fields.Date.today() + timedelta(days=7),
            "sample_ids": [
                Command.create(
                    {
                        "customer_sample_name": "Bắp cải Đà Lạt lô 1018",
                        "sample_type_id": env.ref("sol_demo.demo_sample_type_cabbage").id,
                        "physical_state": "solid",
                        "test_ids": [Command.create({"parameter_id": parameter.id})],
                    }
                )
            ],
        }
    )
    _receive(env, request)
    # The tester role is not rewritten on an existing database, so it may not hold result create. The user stays the
    # tester, which is who the deduction takes stock for.
    result = (
        env[MODEL_TEST_RESULT]
        .with_user(tester)
        .sudo()
        .create({"sample_test_id": request.sample_ids.test_ids.id, "value": 0.012})
    )
    env[MODEL_RESULT_CONTAINER].with_user(tester).sudo().create(
        [
            {"result_id": result.id, "container_id": container.id, "sequence": sequence}
            for sequence, container in enumerate(containers, start=1)
        ]
    )
    result.with_user(tester).sudo().action_sign()
    return result


def _spill(env, tester, container):
    """20 mL spilled from an opened bottle."""
    wizard = (
        env[MODEL_STOCK_USE]
        .with_user(tester)
        .create(
            {
                "kind": "waste",
                "container_id": container.id,
                "item_id": container.item_id.id,
                "lot_id": container.lot_id.id,
                "quantity": 20,
                "scrap_reason_tag_ids": [Command.set([env.ref(SCRAP_SPILLED).id])],
            }
        )
    )
    wizard.action_confirm()
    return env[MODEL_STOCK_MOVE].search(
        [("is_scrap", "=", True), ("move_line_ids.package_id", "=", container.id)], limit=1
    )
