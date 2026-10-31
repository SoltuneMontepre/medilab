from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Command

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_STOCK_PICKING, MODEL_STOCK_QUANT

if TYPE_CHECKING:
    from medilab_model_types import Model_purchase_order as PurchaseOrderBase
else:
    PurchaseOrderBase = object

MARKER = "sol_demo.demo_purchase_order_draft"
STOREKEEPER = "sol_demo.demo_res_users_storekeeper"
LAB_HEAD = "sol_demo.demo_res_users_lab_head"
NITRIC_ACID_CERTIFICATE = "sol_demo.demo_ir_attachment_certificate_nitric_acid"
NITRIC_ACID_LOT = "K55012345"
NITRIC_ACID_EXPIRY = "2027-09-30 00:00:00"
REJECTION_REASON = "Acetonitrile costs more than on the last order; ask Vietnam Chemicals for a new quote."


# Đơn Mua Hàng
class PurchaseOrder(models.Model, PurchaseOrderBase):
    _inherit = MODEL_PURCHASE_ORDER

    @api.model
    def _seed_purchasing_demo(self):
        """Purchase orders in each status of their lifecycle, a receipt of 5 bottles of one nitric acid lot with its
        certificate and a receipt without a purchase order. Safe to run again."""
        if self.env.ref(MARKER, raise_if_not_found=False):
            return
        # The storekeeper buys and the lab head signs last, as the demo approval chain asks; with full rights, so an
        # upgraded database whose roles predate purchasing still gets the demo.
        storekeeper = self.env.ref(STOREKEEPER)
        lab_head = self.env.ref(LAB_HEAD)
        orders = self.with_user(storekeeper).sudo()
        chemicals = self.env.ref("sol_demo.demo_res_partner_vietnam_chemicals")
        labware = self.env.ref("sol_demo.demo_res_partner_labware_supplies")
        chemistry = self.env.ref("sol_demo.demo_hr_department_chemistry")
        microbiology = self.env.ref("sol_demo.demo_hr_department_microbiology")
        item = {
            name: self.env.ref(f"sol_demo.demo_product_product_{name}")
            for name in ("nitric_acid", "nitrile_gloves", "acetonitrile", "sodium_chloride", "agar_plates", "aas_lamp")
        }
        nitric_acid = item["nitric_acid"]
        gloves = item["nitrile_gloves"]

        draft = _order(orders, labware, microbiology, (gloves, 500, 2000))
        requested = _order(orders, chemicals, chemistry, (item["acetonitrile"], 4000, 450))
        requested.action_request_approval()
        rejected = _order(orders, chemicals, chemistry, (item["acetonitrile"], 2000, 520))
        rejected.action_request_approval()
        rejected.with_user(lab_head).sudo().action_reject(REJECTION_REASON)
        signed = _signed(_order(orders, chemicals, chemistry, (item["sodium_chloride"], 2000, 380)), lab_head)
        sent = _signed(_order(orders, labware, microbiology, (item["agar_plates"], 200, 15000)), lab_head)
        sent.action_send_to_supplier()
        cancelled = _signed(_order(orders, labware, microbiology, (gloves, 300, 2100)), lab_head)
        cancelled.action_send_to_supplier()
        cancelled.button_cancel()
        partial = _signed(_order(orders, chemicals, chemistry, (nitric_acid, 5000, 520)), lab_head)
        partial.action_send_to_supplier()
        nitric_acid_receipt = partial.picking_ids
        move = nitric_acid_receipt.move_ids
        move.move_line_ids.unlink()
        move.move_line_ids = [
            Command.create(
                {
                    "product_id": nitric_acid.id,
                    "picking_id": nitric_acid_receipt.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_name": NITRIC_ACID_LOT,
                    "quantity": 2500,
                    "container_count": 5,
                    "expiration_date": fields.Datetime.to_datetime(NITRIC_ACID_EXPIRY),
                    "certificate_id": self.env.ref(NITRIC_ACID_CERTIFICATE).id,
                }
            )
        ]
        move.picked = True
        nitric_acid_receipt.button_validate()
        received = _signed(_order(orders, labware, chemistry, (gloves, 1000, 1900)), lab_head)
        received.action_send_to_supplier()
        received.picking_ids.button_validate()

        receipt_type = self.env.ref("stock.warehouse0").in_type_id
        room = self.env.ref("sol_demo.demo_stock_location_room_101")
        without_order = (
            self.env[MODEL_STOCK_PICKING]
            .with_user(storekeeper)
            .sudo()
            .create(
                {
                    "picking_type_id": receipt_type.id,
                    "partner_id": labware.id,
                    "location_id": receipt_type.default_location_src_id.id,
                    "location_dest_id": room.id,
                    "origin": "Replacement lamp, delivery note 2610/LS",
                    "move_ids": [
                        Command.create(
                            {
                                "product_id": item["aas_lamp"].id,
                                "product_uom_qty": 1,
                                "price_unit": 3200000,
                                "location_id": receipt_type.default_location_src_id.id,
                                "location_dest_id": room.id,
                            }
                        )
                    ],
                }
            )
        )
        without_order.action_confirm()
        without_order.button_validate()

        # Stock in the fridge on a bench of the Chemistry room, beside the stock the receipts put in the central store.
        self.env[MODEL_STOCK_QUANT].sudo()._update_available_quantity(
            item["acetonitrile"], self.env.ref("sol_demo.demo_stock_location_fridge_2"), 4000
        )

        self.env["ir.model.data"]._update_xmlids(
            [
                {"xml_id": f"sol_demo.{name}", "record": record, "noupdate": True}
                for name, record in (
                    ("demo_purchase_order_draft", draft),
                    ("demo_purchase_order_requested", requested),
                    ("demo_purchase_order_rejected", rejected),
                    ("demo_purchase_order_signed", signed),
                    ("demo_purchase_order_sent", sent),
                    ("demo_purchase_order_cancelled", cancelled),
                    ("demo_purchase_order_partially_received", partial),
                    ("demo_purchase_order_received", received),
                    ("demo_stock_picking_nitric_acid", nitric_acid_receipt),
                    ("demo_stock_picking_without_order", without_order),
                    ("demo_stock_lot_nitric_acid", nitric_acid_receipt.move_line_ids.lot_id),
                )
            ]
        )


def _order(orders, supplier, department, line):
    item, quantity, price = line
    return orders.create(
        {
            "partner_id": supplier.id,
            "department_id": department.id,
            "order_line": [Command.create({"product_id": item.id, "product_qty": quantity, "price_unit": price})],
        }
    )


def _signed(order, lab_head):
    order.action_request_approval()
    order.with_user(lab_head).sudo().action_sign()
    return order
