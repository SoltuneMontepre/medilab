from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PRODUCT,
    MODEL_SCRAP_REASON_TAG,
    MODEL_STOCK_LOCATION,
    MODEL_STOCK_LOT,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_USE,
)
from odoo.addons.sol_inventory.constants.stock import CONTAINER_OPENED, CONTAINER_SEALED
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON

USE = "use"
WASTE = "waste"


# Sử Dụng Vật Tư
class StockUse(models.TransientModel):
    _name = MODEL_STOCK_USE
    _description = "Record Use or Waste"

    # use or waste.
    kind = fields.Selection([(USE, "Use"), (WASTE, "Waste")], required=True, default=USE)
    # Code read from a container's label. Empty when the item is kept by lot or by quantity.
    container_scan = fields.Char(string="Container Code")
    # The container the use or waste is taken from. Empty when the item is kept by lot or by quantity.
    container_id = fields.Many2one(MODEL_STOCK_PACKAGE, string="Container")
    # The item, from the container or chosen for a lot or a quantity.
    item_id = fields.Many2one(MODEL_PRODUCT, string="Item", domain=[("item_kind", "!=", False)])
    # The lot, from the container or chosen when the item is kept by lot.
    lot_id = fields.Many2one(MODEL_STOCK_LOT, string="Lot")
    # The store the lot or quantity is taken from. A container brings its own place.
    location_id = fields.Many2one(MODEL_STOCK_LOCATION, string="Store", domain="[('id', 'in', store_ids)]")
    # Stores the signed-in person takes stock from.
    store_ids = fields.Many2many(MODEL_STOCK_LOCATION, string="Stores", compute="_compute_store_ids")
    # Quantity used or wasted, in the item's unit.
    quantity = fields.Float(digits="Product Unit")
    # Why the stock was used. Required for a use; a waste uses a scrap reason instead.
    reason = fields.Char()
    # Why the stock was wasted.
    scrap_reason_tag_ids = fields.Many2many(MODEL_SCRAP_REASON_TAG, string="Waste Reason")

    @api.depends_context("uid")
    def _compute_store_ids(self):
        stores = self.env[MODEL_PERSON]._for_user()._store()
        for wizard in self:
            wizard.store_ids = stores

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        stores = self.env[MODEL_PERSON]._for_user()._store()
        if "location_id" in fields_list and len(stores) == 1:
            defaults["location_id"] = stores.id
        return defaults

    @api.onchange("container_scan")
    def _onchange_container_scan(self):
        code = (self.container_scan or "").strip()
        if not code:
            return
        container = self.env[MODEL_STOCK_PACKAGE]._find_by_code(code)
        self.container_id = container
        self.item_id = container.item_id
        self.lot_id = container.lot_id
        self.quantity = container.quantity
        self.container_scan = False

    @api.onchange("container_id")
    def _onchange_container_id(self):
        if not self.container_id:
            return
        self.item_id = self.container_id.item_id
        self.lot_id = self.container_id.lot_id
        if not self.quantity:
            self.quantity = self.container_id.quantity

    def action_confirm(self):
        """Record a use into Production, or a waste into scrap, from the signed-in person's store."""
        self.ensure_one()
        self._check_can_record()
        if not self.item_id or self.item_id.uom_id.compare(self.quantity, 0) <= 0:
            raise UserError(self.env._("Enter an item and a quantity above zero."))
        person = self.env[MODEL_PERSON]._for_user()
        if self.container_id or self.item_id.track_containers:
            return self._record_container(person)
        return self._record_stock(person)

    def _record_container(self, person):
        container = self.container_id
        if not container:
            raise UserError(self.env._("Scan a container of %s.", self.item_id.display_name))
        if container.item_id != self.item_id:
            raise UserError(
                self.env._(
                    "%(container)s holds %(item)s.",
                    container=container.display_name,
                    item=container.item_id.display_name,
                )
            )
        container._check_in_store(person)
        scrap = self.kind == WASTE
        if scrap:
            self._check_waste(container)
        else:
            if not self.reason:
                raise UserError(self.env._("Give the reason for this use."))
            container._check_for_use(person)
        # A waste may take a sealed container whole, so the checks above replace the checks of a use.
        self.env[MODEL_STOCK_MOVE]._take_containers(
            self.item_id,
            container,
            self.quantity,
            check_use=False,
            scrap=scrap,
            **self._move_values(scrap),
        )
        return {"type": "ir.actions.act_window_close"}

    def _check_waste(self, container):
        if not self.scrap_reason_tag_ids:
            raise UserError(self.env._("Choose why it was wasted."))
        if container.status == CONTAINER_SEALED:
            if self.item_id.uom_id.compare(self.quantity, container.quantity) != 0:
                raise UserError(
                    self.env._(
                        "A sealed container is wasted whole. %(container)s holds %(quantity)s %(unit)s.",
                        container=container.display_name,
                        quantity=container.item_id.uom_id.round(container.quantity),
                        unit=container.item_id.uom_id.name,
                    )
                )
            return
        if container.status != CONTAINER_OPENED:
            raise UserError(self.env._("%s cannot be wasted.", container.display_name))

    def _record_stock(self, person):
        store = self.location_id
        if not store or store._holding_store() not in person._store():
            raise UserError(self.env._("Choose one of your stores."))
        if self.item_id.tracking in ("lot", "serial") and not self.lot_id:
            raise UserError(self.env._("Choose the lot of %s.", self.item_id.display_name))
        scrap = self.kind == WASTE
        if scrap and not self.scrap_reason_tag_ids:
            raise UserError(self.env._("Choose why it was wasted."))
        if not scrap and not self.reason:
            raise UserError(self.env._("Give the reason for this use."))
        self.env[MODEL_STOCK_MOVE]._take_quants(
            self.item_id, store, self.quantity, lot=self.lot_id, scrap=scrap, **self._move_values(scrap)
        )
        return {"type": "ir.actions.act_window_close"}

    def _move_values(self, scrap):
        """What the move records: the reason of a use, named as its reference, or the scrap reasons of a waste, whose
        reference Odoo numbers."""
        if scrap:
            return {"automatic": False, "scrap_reason_tag_ids": self.scrap_reason_tag_ids}
        return {"automatic": False, "reason": self.reason, "reference": self.reason}

    def _check_can_record(self):
        moves = self.env[MODEL_STOCK_MOVE]
        if not self.env.su and "all" not in moves._user_scopes("create"):
            raise AccessError(self.env._("You are not allowed to record a use or a waste."))
