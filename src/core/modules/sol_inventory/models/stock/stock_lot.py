from lxml import etree

from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER, MODEL_STOCK_LOT, MODEL_STOCK_PICKING
from odoo.addons.sol_inventory.constants.stock import LOT_AVAILABLE, LOT_DISPOSED, LOT_EXPIRED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_PERMISSION_MIXIN,
)

# Stat buttons of Odoo's lot form and the model of the documents each counts.
DOCUMENT_BUTTONS = {
    "action_view_po": MODEL_PURCHASE_ORDER,
    # Added by Odoo's sale_stock once E-commerce is installed too.
    "action_view_so": "sale.order",
    "action_lot_open_transfers": MODEL_STOCK_PICKING,
}


# Lô
class StockLot(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_LOT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_LOT, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    # Receipts create lots; the storekeeper corrects them or adds their certificate later.
    _permission_actions = ("edit",)

    # available, expired or disposed. An expired lot cannot be used.
    status = fields.Selection(
        [(LOT_AVAILABLE, "Available"), (LOT_EXPIRED, "Expired"), (LOT_DISPOSED, "Disposed")],
        required=True,
        default=LOT_AVAILABLE,
    )
    # The manufacturer's certificate that came with the lot.
    certificate_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="Manufacturer's Certificate", ondelete="set null")

    _status_expiry_idx = models.Index("(status, expiration_date)")

    def action_open_containers(self):
        return self.sudo().quant_ids.package_id.with_env(self.env)._action_open()

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id, view_type, **options)
        # Every internal user reads lots, but only some read the orders and transfers Odoo counts on them; counting
        # documents the user cannot read fails, so their buttons are left out.
        hidden = {
            method
            for method, model in DOCUMENT_BUTTONS.items()
            if model in self.env and not self.env[model].has_access("read")
        }
        if view_type == "form" and hidden:
            root = etree.fromstring(result["arch"])
            for button in list(root.iter("button")):
                parent = button.getparent()
                if button.get("name") in hidden and parent is not None:
                    parent.remove(button)
            result["arch"] = etree.tostring(root, encoding="unicode")
        return result
