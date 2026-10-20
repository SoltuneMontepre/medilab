import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.fields import Command

from odoo.addons.sol_demo.models.purchasing.purchase_order import LAB_HEAD, STOREKEEPER, _order, _signed
from odoo.addons.sol_demo.models.stock.stock_package import STORE, TESTER, _container, _lot
from odoo.addons.sol_demo.models.stock.stock_warehouse_orderpoint import CENTRAL
from odoo.addons.sol_inventory.constants.models import (
    MODEL_PURCHASE_ORDER,
    MODEL_STOCK_CORRECTION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_QUANT,
    MODEL_STOCK_RELOCATION,
    MODEL_STOCK_USE,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED

_logger = logging.getLogger(__name__)

MARKER = "sol_demo.demo_stock_move_relocation_fridge"
FRIDGE = "sol_demo.demo_stock_location_fridge_1"
PLATES_LOT = "PCA-2610"
# Agar plates of the order sent to Labware arrive half at a time, and expire within the warning.
PLATES_RECEIVED = 100
PLATES_EXPIRE_IN_DAYS = 20


# Tồn Kho
class StockQuant(models.Model):
    _inherit = MODEL_STOCK_QUANT

    @api.model
    def _seed_stock_demo(self):
        """Stock moved inside a store, used by hand, corrected, expired, expiring soon, disposed of and below its
        minimum, and gloves received twice at different prices. Safe to run again."""
        if self.env.ref(MARKER, raise_if_not_found=False):
            return
        storekeeper = self.env.ref(STOREKEEPER)
        tester = self.env.ref(TESTER)
        central = self.env.ref(CENTRAL)
        store = self.env.ref(STORE)
        if central.manager_id.user_id != storekeeper or not self.env.ref(
            "sol_demo.demo_stock_package_distilled_water", raise_if_not_found=False
        ):
            _logger.info("The demo stores or containers are not seeded, so no stock moves are seeded.")
            return
        plates = self.env.ref("sol_demo.demo_product_product_agar_plates")
        gloves = self.env.ref("sol_demo.demo_product_product_nitrile_gloves")
        acetonitrile = self.env.ref("sol_demo.demo_product_product_acetonitrile")
        salt = self.env.ref("sol_demo.demo_product_product_sodium_chloride")

        plates_lot = _receive_plates(self.env, plates)
        relocation = self._as(storekeeper, MODEL_STOCK_RELOCATION).create(
            {
                "item_id": plates.id,
                "lot_id": plates_lot.id,
                "location_id": central.id,
                "location_dest_id": self.env.ref(FRIDGE).id,
                "quantity": PLATES_RECEIVED,
                "reason": "Agar plates are kept at 2–8 °C",
            }
        )
        relocation.action_confirm()
        self._as(storekeeper, MODEL_STOCK_CORRECTION).create(
            {
                "item_id": plates.id,
                "lot_id": plates_lot.id,
                "location_id": self.env.ref(FRIDGE).id,
                "counted_quantity": PLATES_RECEIVED - 2,
                "reason": "Two plates cracked in the fridge",
            }
        ).action_confirm()
        self._as(tester, MODEL_STOCK_USE).create(
            {
                "kind": "use",
                "container_id": self.env.ref("sol_demo.demo_stock_package_distilled_water").id,
                "item_id": self.env.ref("sol_demo.demo_product_product_distilled_water").id,
                "quantity": 50,
                "reason": "Calibration of the pH meter",
            }
        ).action_confirm()

        _receive_gloves(self.env)
        # Gloves for the quarterly cleaning take the central store below its minimum of 200.
        self._as(storekeeper, MODEL_STOCK_USE).create(
            {
                "kind": "use",
                "item_id": gloves.id,
                "location_id": central.id,
                "quantity": 1350,
                "reason": "Quarterly cleaning of the laboratory",
            }
        ).action_confirm()

        # A bottle opened past its shelf life after opening waits for disposal; so does the expired acetonitrile lot.
        salt_bottle = _container(self.env, _lot(self.env, salt, "NaCl-2509", 365), 1, 500, store)
        salt_bottle.write(
            {
                "status": CONTAINER_OPENED,
                "opened_at": fields.Datetime.now() - timedelta(days=200),
                "opened_by_id": tester.id,
            }
        )
        disposed = _container(self.env, _lot(self.env, acetonitrile, "ACN-2412", -30), 1, 1000, store)
        quants = self.search([("package_id", "=", disposed.id)])
        quants.with_user(storekeeper).action_dispose()

        moves = self.env[MODEL_STOCK_MOVE]
        self.env["ir.model.data"]._update_xmlids(
            [
                {"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True}
                for name, record in (
                    ("demo_stock_lot_agar_plates", plates_lot),
                    ("demo_stock_package_sodium_chloride_expired", salt_bottle),
                    ("demo_stock_package_acetonitrile_disposed", disposed),
                    ("demo_stock_lot_acetonitrile_disposed", disposed.lot_id),
                    ("demo_stock_move_relocation_fridge", moves.search([("reason", "=", relocation.reason)], limit=1)),
                )
            ]
        )

    def _as(self, user, model):
        return self.env[model].with_user(user)


def _receive_plates(env, plates):
    """Half the agar plates of the order sent to Labware arrive, in a lot that expires within the warning."""
    order = env.ref("sol_demo.demo_purchase_order_sent")
    receipt = order.picking_ids.filtered(lambda picking: picking.state not in ("done", "cancel"))[:1]
    move = receipt.move_ids
    move.move_line_ids.unlink()
    move.move_line_ids = [
        Command.create(
            {
                "product_id": plates.id,
                "picking_id": receipt.id,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "lot_name": PLATES_LOT,
                "quantity": PLATES_RECEIVED,
                "expiration_date": fields.Datetime.now() + timedelta(days=PLATES_EXPIRE_IN_DAYS),
            }
        )
    ]
    move.picked = True
    receipt.button_validate()
    return move.move_line_ids.lot_id


def _receive_gloves(env):
    """A second order of gloves, received at a higher price than the first, so the costing methods differ."""
    orders = env[MODEL_PURCHASE_ORDER].with_user(env.ref(STOREKEEPER)).sudo()
    order = _signed(
        _order(
            orders,
            env.ref("sol_demo.demo_res_partner_labware_supplies"),
            env.ref("sol_demo.demo_hr_department_chemistry"),
            (env.ref("sol_demo.demo_product_product_nitrile_gloves"), 500, 2200),
        ),
        env.ref(LAB_HEAD),
    )
    order.action_send_to_supplier()
    order.picking_ids.button_validate()
    env["ir.model.data"]._update_xmlids(
        [{"xml_id": "sol_demo.demo_purchase_order_received_2", "record": order, "noupdate": True}]
    )
