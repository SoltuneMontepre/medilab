from datetime import datetime

from odoo.fields import Command

from .catalog_case import CatalogCase
from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_STOCK_PICKING
from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_IR_ATTACHMENT,
    MODEL_ROLE,
)

# What the storekeeper is given to buy and receive stock.
PURCHASING_PERMISSIONS = (
    "purchase_order.read.all",
    "purchase_order.create.all",
    "purchase_order.edit.all",
    "purchase_order.delete.all",
    "purchase_order.sign.all",
    "receipt.read.all",
    "receipt.create.all",
    "receipt.edit.all",
    "lot.edit.all",
)


class PurchasingCase(CatalogCase):
    """A storekeeper who buys and receives stock, a lab head who signs purchase orders last, and receipts that land in
    the central store."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receipt_type = cls.env.ref("stock.warehouse0").in_type_id
        cls.receipt_type.default_location_dest_id = cls.central
        cls.grant_inventory(cls.storekeeper, *PURCHASING_PERMISSIONS)
        cls.lab_head = cls.create_person("Le Thi Duyet", cls.chemistry, "duyet.le")
        cls.grant_inventory(cls.lab_head, "purchase_order.read.all", "purchase_order.sign.all")
        cls.buyer = cls.storekeeper.user_id
        cls.signer = cls.lab_head.user_id
        cls.setup_signing_chain()
        cls.vendor = cls.supplier.partner_id
        cls.acid.use_expiration_date = True

    @classmethod
    def setup_signing_chain(cls):
        """The storekeeper signs first and the lab head last. The demo data may have made the chain."""
        chain = cls.env[MODEL_APPROVAL_CHAIN].search(
            [("document_model", "=", MODEL_PURCHASE_ORDER), ("purpose", "=", PURPOSE_SIGNING)]
        )
        if not chain:
            chain = cls.env[MODEL_APPROVAL_CHAIN].create(
                {"document_model": MODEL_PURCHASE_ORDER, "purpose": PURPOSE_SIGNING, "name": "Purchase order signing"}
            )
            for sequence, name, code in ((10, "Storekeeper", "po_storekeeper"), (20, "Lab head", "po_lab_head")):
                role = cls.env[MODEL_ROLE].create({"code": code, "name": name})
                cls.env[MODEL_APPROVAL_LEVEL].create(
                    {"chain_id": chain.id, "sequence": sequence, "name": name, "role_id": role.id, "can_reject": True}
                )
        first_level, last_level = chain.level_ids.sorted("sequence")
        cls.storekeeper.role_ids = first_level.role_id
        cls.lab_head.role_ids = last_level.role_id

    @classmethod
    def make_order(cls, *lines, user=None, **vals):
        """A draft purchase order to the supplier, created by the storekeeper, with (item, quantity, price) lines."""
        return (
            cls.env[MODEL_PURCHASE_ORDER]
            .with_user(user or cls.buyer)
            .create(
                {
                    "partner_id": cls.vendor.id,
                    "order_line": [
                        Command.create({"product_id": item.id, "product_qty": quantity, "price_unit": price})
                        for item, quantity, price in lines
                    ],
                    **vals,
                }
            )
        )

    @classmethod
    def signed_order(cls, *lines, **vals):
        order = cls.make_order(*lines, **vals)
        order.action_request_approval()
        order.with_user(cls.signer).action_sign()
        return order

    @classmethod
    def sent_order(cls, *lines, **vals):
        order = cls.signed_order(*lines, **vals)
        order.action_send_to_supplier()
        return order

    @classmethod
    def make_receipt(cls, *lines, location=None):
        """A confirmed receipt without a purchase order from the supplier, with (item, quantity, price) lines."""
        location = location or cls.central
        receipt = (
            cls.env[MODEL_STOCK_PICKING]
            .with_user(cls.buyer)
            .create(
                {
                    "picking_type_id": cls.receipt_type.id,
                    "partner_id": cls.vendor.id,
                    "location_id": cls.receipt_type.default_location_src_id.id,
                    "location_dest_id": location.id,
                    "move_ids": [
                        Command.create(
                            {
                                "product_id": item.id,
                                "product_uom_qty": quantity,
                                "price_unit": price,
                                "location_id": cls.receipt_type.default_location_src_id.id,
                                "location_dest_id": location.id,
                            }
                        )
                        for item, quantity, price in lines
                    ],
                }
            )
        )
        receipt.action_confirm()
        return receipt

    @classmethod
    def fill(cls, picking, item, *lots):
        """Set what arrived of the item on the receipt: (lot name, quantity, containers, expiry, certificate) lots."""
        move = picking.move_ids.filtered(lambda move: move.product_id == item)
        move.move_line_ids.unlink()
        move.move_line_ids = [
            Command.create(
                {
                    "product_id": item.id,
                    "picking_id": picking.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "lot_name": lot_name,
                    "quantity": quantity,
                    "container_count": containers,
                    "expiration_date": expiry,
                    "certificate_id": certificate.id if certificate else False,
                }
            )
            for lot_name, quantity, containers, expiry, certificate in lots
        ]
        move.picked = True
        return move

    @classmethod
    def certificate(cls, name="Certificate Lot123.pdf"):
        return (
            cls.env[MODEL_IR_ATTACHMENT]
            .with_user(cls.buyer)
            .create({"name": name, "raw": b"%PDF-1.4 certificate", "mimetype": "application/pdf"})
        )

    @staticmethod
    def expiry(day="2028-06-30"):
        return datetime.fromisoformat(day)
