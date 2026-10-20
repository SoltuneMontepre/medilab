from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PRODUCT,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_OPERATION,
    MODEL_STOCK_PACKAGE,
)
from odoo.addons.sol_inventory.constants.stock import IN_STOCK_STATUSES


# The container, or the item, lot and location, a dialog that keeps the stock of a store acts on, and its reason.
class StockOperation(models.AbstractModel):
    _name = MODEL_STOCK_OPERATION
    _description = "Stock Operation"

    # Code read from a container's label. Empty when a lot or a quantity is chosen.
    container_scan = fields.Char(string="Container Code")
    # The container acted on. Empty when a lot or a quantity is chosen.
    container_id = fields.Many2one(
        MODEL_STOCK_PACKAGE, string="Container", domain=[("status", "in", IN_STOCK_STATUSES)]
    )
    # The item, from the container or chosen.
    item_id = fields.Many2one(MODEL_PRODUCT, string="Item", domain=[("item_kind", "!=", False)])
    # The lot, from the container or chosen.
    lot_id = fields.Many2one(MODEL_STOCK_LOT, string="Lot", domain="[('product_id', '=', item_id)]")
    # The location the stock is at. A container brings its own.
    location_id = fields.Many2one(
        MODEL_STOCK_LOCATION,
        string="Location",
        domain="[('usage', '=', 'internal'), ('id', 'child_of', store_ids)]",
    )
    # Stores the signed-in person keeps.
    store_ids = fields.Many2many(MODEL_STOCK_LOCATION, string="Stores", compute="_compute_store_ids")
    # Why the stock is acted on.
    reason = fields.Char()

    @api.depends_context("uid")
    def _compute_store_ids(self):
        stores = self.env[MODEL_STOCK_LOCATION]._kept_by_user()
        for wizard in self:
            wizard.store_ids = stores

    @api.onchange("container_scan")
    def _onchange_container_scan(self):
        if self.container_scan:
            self.container_id = self.env[MODEL_STOCK_PACKAGE]._find_by_code(self.container_scan)
            self.container_scan = False

    @api.onchange("container_id")
    def _onchange_container_id(self):
        if self.container_id:
            self.item_id = self.container_id.item_id
            self.lot_id = self.container_id.lot_id
            self.location_id = self._location()

    def _location(self):
        # A container whose stock ran out has no location left; the one chosen applies then.
        return self.container_id.sudo().location_id or self.location_id

    def _check_operation(self, denied):
        """Refuse a person who may not create moves, a missing item, location or reason, and a location outside the
        stores the person keeps. A scanned container brings its item and lot."""
        self.ensure_one()
        self.env[MODEL_STOCK_MOVE]._check_can_create(denied)
        if self.container_id:
            self.write({"item_id": self.container_id.item_id.id, "lot_id": self.container_id.lot_id.id})
        location = self._location()
        if not location or not self.item_id:
            raise UserError(self.env._("Scan a container, or choose an item and its location."))
        if not (self.reason or "").strip():
            raise UserError(self.env._("Give the reason."))
        # As the person, since a container's location is read with full rights.
        location.with_env(self.env)._check_kept_by_user()
        return location
