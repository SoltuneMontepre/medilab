from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_inventory.constants.items import TRACKING_LOT
from odoo.addons.sol_inventory.constants.models import (
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_OPERATION,
    MODEL_STOCK_QUANT,
    MODEL_STOCK_RELOCATION,
)
from odoo.addons.sol_inventory.constants.stock import IN_STOCK_STATUSES, INTERNAL_USAGE


# Chuyển Vị Trí
class StockRelocation(models.TransientModel):
    _name = MODEL_STOCK_RELOCATION
    _inherit = MODEL_STOCK_OPERATION
    _description = "Move Stock"

    # The location the stock is taken from. A container brings its own.
    location_id = fields.Many2one(string="From Location")
    # The location of the same store the stock is put in.
    location_dest_id = fields.Many2one(
        MODEL_STOCK_LOCATION,
        string="To Location",
        domain="[('usage', '=', 'internal'), ('id', 'child_of', store_ids)]",
    )
    # Quantity moved, in the item's unit; a container, or every container of a lot, moves whole.
    quantity = fields.Float(string="Quantity to Move", digits="Product Unit")

    @api.onchange("container_id")
    def _onchange_container_id(self):
        result = super()._onchange_container_id()
        if self.container_id:
            self.quantity = self.container_id.quantity
        return result

    def action_confirm(self):
        """Move the container, lot or quantity to another location of the same store. A container keeps its status and
        usable date."""
        source = self._check_operation(self.env._("You are not allowed to move stock."))
        dest = self.location_dest_id
        if not dest:
            raise UserError(self.env._("Choose where the stock goes."))
        store = source._holding_store()
        if dest.usage != INTERNAL_USAGE or dest._holding_store() != store:
            raise UserError(
                self.env._(
                    "%(location)s is not in %(store)s. Stock goes to another store through a requisition or a "
                    "transfer.",
                    location=dest.display_name,
                    store=store.display_name,
                )
            )
        if source == dest:
            raise UserError(self.env._("The stock is already in %s.", source.display_name))
        self.env[MODEL_STOCK_MOVE]._done_moves(
            self.item_id, self._takes(source), dest, automatic=False, reason=self.reason, reference=self.reason
        )
        return {"type": "ir.actions.act_window_close"}

    def _takes(self, source):
        """What leaves the source location: a container whole, every container of a lot, or a quantity."""
        item = self.item_id
        if self.container_id:
            return [self._container_take(self.container_id)]
        if not item.track_containers:
            return self._quantity_takes(source)
        if not self.lot_id:
            raise UserError(self.env._("Scan a container of %s, or choose its lot.", item.display_name))
        containers = self._quants(source, in_containers=True).package_id
        if not containers:
            raise UserError(
                self.env._(
                    "%(location)s holds no container of lot %(lot)s.",
                    location=source.display_name,
                    lot=self.lot_id.name,
                )
            )
        return [self._container_take(container) for container in containers]

    def _container_take(self, container):
        if container.item_id != self.item_id or container.status not in IN_STOCK_STATUSES:
            raise UserError(self.env._("%s cannot be moved.", container.display_name))
        return {
            "location": container.sudo().location_id,
            "quantity": container.quantity,
            "lot": container.lot_id,
            "package": container,
            "result_package": container,
        }

    def _quantity_takes(self, source):
        item = self.item_id
        if item.uom_id.compare(self.quantity, 0) <= 0:
            raise UserError(self.env._("Enter a quantity above zero."))
        if item.tracking == TRACKING_LOT and not self.lot_id:
            raise UserError(self.env._("Choose the lot of %s.", item.display_name))
        remaining = self.quantity
        takes = []
        for quant in self._quants(source, in_containers=False):
            if item.uom_id.compare(remaining, 0) <= 0:
                break
            taken = min(remaining, quant.quantity)
            takes.append({"location": source, "quantity": taken, "lot": quant.lot_id})
            remaining = item.uom_id.round(remaining - taken)
        if item.uom_id.compare(remaining, 0) > 0:
            raise UserError(
                self.env._(
                    "%(location)s holds only %(held)s %(unit)s of %(item)s.",
                    location=source.display_name,
                    held=item.uom_id.round(self.quantity - remaining),
                    unit=item.uom_id.name,
                    item=item.display_name,
                )
            )
        return takes

    def _quants(self, location, in_containers):
        """The stock of the item, of the lot when one is chosen, kept right at this location, in containers or not."""
        domain = (
            Domain("product_id", "=", self.item_id.id)
            & Domain("location_id", "=", location.id)
            & Domain("quantity", ">", 0)
            & Domain("package_id", "!=" if in_containers else "=", False)
        )
        if self.lot_id:
            domain &= Domain("lot_id", "=", self.lot_id.id)
        return self.env[MODEL_STOCK_QUANT].sudo().search(domain, order="in_date, id")
