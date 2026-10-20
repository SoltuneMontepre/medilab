from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_inventory.constants.items import TRACKING_LOT
from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_CORRECTION, MODEL_STOCK_OPERATION, MODEL_STOCK_QUANT


# Điều Chỉnh Tồn Kho
class StockCorrection(models.TransientModel):
    _name = MODEL_STOCK_CORRECTION
    _inherit = MODEL_STOCK_OPERATION
    _description = "Correct Quantity"

    # Quantity on record at the location, in the item's unit.
    on_hand = fields.Float(string="On Hand", digits="Product Unit", compute="_compute_on_hand")
    # Quantity actually there, in the item's unit.
    counted_quantity = fields.Float(string="Counted Quantity", digits="Product Unit")

    @api.depends("container_id", "item_id", "lot_id", "location_id")
    def _compute_on_hand(self):
        for wizard in self:
            quants = wizard._quant() if wizard._location() and wizard.item_id else []
            wizard.on_hand = sum(quant.quantity for quant in quants)

    @api.onchange("container_id")
    def _onchange_container_id(self):
        result = super()._onchange_container_id()
        if self.container_id:
            self.counted_quantity = self.container_id.quantity
        return result

    def action_confirm(self):
        """Correct the quantity on record to the quantity counted, with Odoo's inventory adjustment. Its move names the
        reason; a container left empty is depleted."""
        location = self._check_operation(self.env._("You are not allowed to correct stock."))
        item = self.item_id
        if item.track_containers and not self.container_id:
            raise UserError(self.env._("Scan the container of %s to correct.", item.display_name))
        if item.tracking == TRACKING_LOT and not self.lot_id:
            raise UserError(self.env._("Choose the lot of %s.", item.display_name))
        if item.uom_id.compare(self.counted_quantity, 0) < 0:
            raise UserError(self.env._("The counted quantity cannot be negative."))
        if item.uom_id.compare(self.counted_quantity, self.on_hand) == 0:
            raise UserError(
                self.env._(
                    "%(location)s already holds %(quantity)s %(unit)s.",
                    location=location.display_name,
                    quantity=item.uom_id.round(self.on_hand),
                    unit=item.uom_id.name,
                )
            )
        quant = self._quant()[:1] or self._new_quant(location)
        quant.inventory_quantity = self.counted_quantity
        quant.with_context(inventory_name=self.reason)._apply_inventory()
        return {"type": "ir.actions.act_window_close"}

    def _quant(self):
        domain = (
            Domain("product_id", "=", self.item_id.id)
            & Domain("location_id", "=", self._location().id)
            & Domain("package_id", "=", self.container_id.id)
            & Domain("lot_id", "=", self.lot_id.id)
        )
        return self.env[MODEL_STOCK_QUANT].sudo().search(domain)

    def _new_quant(self, location):
        """A quant for stock found where none is on record."""
        return (
            self.env[MODEL_STOCK_QUANT]
            .sudo()
            .with_context(inventory_mode=True)
            .create({"product_id": self.item_id.id, "location_id": location.id, "lot_id": self.lot_id.id})
        )
