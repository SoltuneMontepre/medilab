from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_ORDERPOINT,
    MODEL_PREPARATION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import (
    DONE,
    INTERNAL_USAGE,
    LOT_AVAILABLE,
    MOVE_ADJUSTMENT,
    MOVE_CONSUMPTION,
    MOVE_DISPOSAL,
    MOVE_PREPARATION,
    MOVE_RECEIPT,
    MOVE_RELOCATION,
    MOVE_WASTE,
    PRODUCTION_USAGE,
    RECEIPT_CODE,
)
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_EXPIRED, SCRAP_OTHER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TEST_RESULT,
)

# What a done move recorded. A mistake is corrected by another move.
DONE_MOVE_FIELDS = frozenset(
    {"product_id", "product_uom_qty", "quantity", "location_id", "location_dest_id", "move_line_ids"}
)


# Dịch Chuyển Kho
class StockMove(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_MOVE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_MOVE, MODEL_PERMISSION_MIXIN]
    # Reading moves, and recording a use, a waste, a relocation, a correction or a disposal. There is no edit
    # permission: a done move is never changed.
    _permission_actions = ("read", "create")

    # receipt, preparation, consumption, waste, adjustment, relocation or disposal, from what the move itself does;
    # empty for any other move.
    move_kind = fields.Selection(
        [
            (MOVE_RECEIPT, "Receipt"),
            (MOVE_PREPARATION, "Preparation"),
            (MOVE_CONSUMPTION, "Consumption"),
            (MOVE_WASTE, "Waste"),
            (MOVE_ADJUSTMENT, "Adjustment"),
            (MOVE_RELOCATION, "Relocation"),
            (MOVE_DISPOSAL, "Disposal"),
        ],
        string="Kind",
        compute="_compute_move_kind",
        store=True,
        precompute=True,
        index=True,
    )
    # The preparation this move belongs to; empty for a use, a waste or a receipt.
    preparation_id = fields.Many2one(
        MODEL_PREPARATION, string="Preparation", copy=False, index=True, ondelete="restrict"
    )
    # The result whose usual use this move deducted; empty when nobody signed a result for it.
    test_result_id = fields.Many2one(
        MODEL_TEST_RESULT, string="Test Result", copy=False, index=True, ondelete="restrict"
    )
    # True when signing a result recorded the move, false when a person recorded it.
    automatic = fields.Boolean(copy=False)
    # Why the stock was used or marked empty. A waste uses scrap reason tags instead.
    reason = fields.Char(copy=False)

    @api.depends(
        "is_scrap",
        "scrap_reason_tag_ids",
        "is_inventory",
        "preparation_id",
        "location_id.usage",
        "location_dest_id.usage",
        "picking_id",
        "picking_id.picking_type_id.code",
        "purchase_line_id",
    )
    def _compute_move_kind(self):
        expired = self.env.ref(SCRAP_EXPIRED, raise_if_not_found=False)
        for move in self:
            move.move_kind = move._kind(expired)

    def _kind(self, expired):
        self.ensure_one()
        if self.is_scrap:
            return MOVE_DISPOSAL if expired and expired in self.scrap_reason_tag_ids else MOVE_WASTE
        if self.preparation_id:
            return MOVE_PREPARATION
        if self.location_dest_id.usage == PRODUCTION_USAGE:
            return MOVE_CONSUMPTION
        if self.purchase_line_id or self.picking_id.picking_type_id.code == RECEIPT_CODE:
            return MOVE_RECEIPT
        if self.is_inventory:
            return MOVE_ADJUSTMENT
        if not self.picking_id and self.location_id.usage == self.location_dest_id.usage == INTERNAL_USAGE:
            return MOVE_RELOCATION
        return False

    def write(self, vals):
        # No move.edit permission exists. The access check still applies, then the write is sudo so the permission
        # mixin does not ask for an edit permission, the same way a receipt is validated.
        if DONE_MOVE_FIELDS & set(vals) and any(move.state == DONE for move in self):
            raise UserError(self.env._("Done moves are never changed; correct a mistake with another move."))
        if self and not self.env.su:
            self.check_access("write")
        return super(StockMove, self.sudo()).write(vals)

    def _action_done(self, cancel_backorder=False):
        done = super()._action_done(cancel_backorder=cancel_backorder)
        finished = self.filtered(lambda move: move.state == DONE)
        finished._settle_containers()
        finished._warn_below_minimum()
        return done

    def _settle_containers(self):
        for move in self:
            move.move_line_ids.package_id._settle(move.is_scrap)

    @api.model
    def _check_can_create(self, message):
        """Refuse a person without the permission to create moves."""
        if not self.env.su and "all" not in self._user_scopes("create"):
            raise AccessError(message)

    def _take_containers(self, item, containers, quantity, *, scrap=False, check_use=True, person=None, **vals):
        """Use or waste quantity of item from these containers, in order, and finish the moves. The containers are
        checked as opened, usable and in the person's store unless the caller checked them its own way."""
        if check_use:
            containers._check_for_use(person or self.env[MODEL_PERSON]._for_user())
        wrong = containers.filtered(lambda container: container.item_id != item)
        if wrong:
            raise UserError(
                self.env._(
                    "%(containers)s do not hold %(item)s.",
                    containers=format_list(self.env, wrong.mapped("display_name")),
                    item=item.display_name,
                )
            )
        takes = self._plan_containers(item, containers, quantity)
        return self._done_moves(item, takes, self._destination(item, scrap), scrap=scrap, **vals)

    def _take_quants(self, item, stores, quantity, *, lot=None, scrap=False, **vals):
        """Use or waste quantity of an item kept by lot or by quantity, from these stores."""
        if item.track_containers:
            raise UserError(self.env._("Scan a container of %s.", item.display_name))
        takes = self._plan_quants(item, stores, quantity, lot=lot)
        return self._done_moves(item, takes, self._destination(item, scrap), scrap=scrap, **vals)

    @api.model
    def _waste_reason(self, tags, reason):
        """The written reason a waste records: required when its reasons include Other, and kept only then."""
        if self.env.ref(SCRAP_OTHER) not in tags._origin:
            return False
        reason = (reason or "").strip()
        if not reason:
            raise UserError(self.env._("Write what happened, since the waste reason is Other."))
        return reason

    def _destination(self, item, scrap):
        if scrap:
            location = self.env.company.sudo().scrap_location_id
            if not location:
                raise UserError(self.env._("Set the company's scrap location before wasting stock."))
            return location
        location = item.product_tmpl_id.with_company(self.env.company).sudo().property_stock_production
        if not location:
            raise UserError(self.env._("Set the company's Production location before using stock."))
        return location

    def _plan_containers(self, item, containers, quantity):
        """How much to take from each container, earlier ones first, without going below zero."""
        remaining = quantity
        takes = []
        for container in containers:
            if item.uom_id.compare(remaining, 0) <= 0:
                break
            available = container.quantity
            if item.uom_id.compare(available, 0) <= 0:
                continue
            taken = remaining if item.uom_id.compare(available, remaining) > 0 else available
            takes.append(
                {
                    "location": container.sudo().location_id,
                    "quantity": taken,
                    "lot": container.lot_id,
                    "package": container,
                }
            )
            remaining = item.uom_id.round(remaining - taken)
        if item.uom_id.compare(remaining, 0) > 0:
            raise UserError(
                self.env._(
                    "%(item)s still needs %(quantity)s %(unit)s. Scan another opened container.",
                    item=item.display_name,
                    quantity=self._amount(item, remaining),
                    unit=item.uom_id.name,
                )
            )
        return takes

    def _plan_quants(self, item, stores, quantity, lot=None):
        """How much to take from each lot in these stores. The earliest usable expiry goes first, and a lot with no
        expiry goes last."""
        domain = Domain(
            [
                ("product_id", "=", item.id),
                ("location_id", "child_of", stores.ids),
                ("quantity", ">", 0),
                ("package_id", "=", False),
            ]
        )
        if lot:
            domain &= Domain("lot_id", "=", lot.id)
        quants = self.env[MODEL_STOCK_QUANT].sudo().search(domain)
        quants = quants.filtered(
            lambda quant: quant.location_id._holding_store() in stores and self._quant_usable(item, quant)
        )
        quants = quants.sorted(key=self._quant_order)
        remaining = quantity
        held = 0.0
        takes = []
        for quant in quants:
            held = item.uom_id.round(held + quant.quantity)
            if item.uom_id.compare(remaining, 0) <= 0:
                continue
            taken = remaining if item.uom_id.compare(quant.quantity, remaining) > 0 else quant.quantity
            takes.append(
                {"location": quant.location_id, "quantity": taken, "lot": quant.lot_id, "package": quant.package_id}
            )
            remaining = item.uom_id.round(remaining - taken)
        if item.uom_id.compare(remaining, 0) > 0:
            raise UserError(
                self.env._(
                    "%(stores)s holds %(held)s %(unit)s of %(item)s that can be used, short of %(needed)s %(unit)s.",
                    stores=format_list(self.env, stores.mapped("display_name")),
                    held=self._amount(item, held),
                    needed=self._amount(item, quantity),
                    unit=item.uom_id.name,
                    item=item.display_name,
                )
            )
        return takes

    def _quant_usable(self, item, quant):
        lot = quant.lot_id
        if item.tracking in ("lot", "serial") and (not lot or lot.status != LOT_AVAILABLE):
            return False
        packages = self.env[MODEL_STOCK_PACKAGE]
        dated = lot and lot.expiration_date and packages._as_date(lot.expiration_date) < packages._today()
        return not (lot and lot.status != LOT_AVAILABLE) and not dated

    @api.model
    def _quant_order(self, quant):
        expiry = quant.lot_id.expiration_date
        return (expiry is False, expiry or fields.Datetime.to_datetime("9999-12-31"), quant.lot_id.id, quant.id)

    def _done_moves(self, item, takes, dest, *, scrap=False, **vals):
        """One done move per source location."""
        grouped = defaultdict(list)
        for take in takes:
            grouped[take["location"]].append(take)
        moves = self.browse()
        for location, group in grouped.items():
            moves |= self._done_move(item, location, dest, group, scrap=scrap, **vals)
        return moves

    def _done_move(self, item, location, dest, takes, *, scrap=False, **vals):
        total = item.uom_id.round(sum(take["quantity"] for take in takes))
        extra = dict(vals)
        tags = extra.pop("scrap_reason_tag_ids", None)
        lines = [
            Command.create(
                {
                    "product_id": item.id,
                    "quantity": take["quantity"],
                    "location_id": location.id,
                    "location_dest_id": dest.id,
                    "lot_id": take["lot"].id if take.get("lot") else False,
                    "package_id": take["package"].id if take.get("package") else False,
                    "result_package_id": take["result_package"].id if take.get("result_package") else False,
                    "picked": True,
                }
            )
            for take in takes
        ]
        create_vals = {
            "product_id": item.id,
            "product_uom_qty": total,
            "location_id": location.id,
            "location_dest_id": dest.id,
            "company_id": self.env.company.id,
            "picked": True,
            "move_line_ids": lines,
            **extra,
        }
        if tags:
            create_vals["scrap_reason_tag_ids"] = [Command.set(tags.ids)]
        if scrap:
            create_vals["is_scrap"] = True
        move = self.sudo().create(create_vals)
        if scrap:
            move._action_scrap()
        else:
            move.move_line_ids.picked = True
            move._action_done()
        return move

    @api.model
    def _amount(self, item, quantity):
        return item.uom_id.round(quantity)

    def _warn_below_minimum(self):
        """Warn about each store whose stock of an item these moves took below its minimum quantity. Moves between the
        locations of one store leave its stock unchanged."""
        taken = defaultdict(float)
        for move in self.sudo():
            if move.location_id.usage != INTERNAL_USAGE:
                continue
            store = move.location_id._holding_store()
            if store and move.location_dest_id._holding_store() != store:
                taken[move.product_id.id, store.id] += move.product_qty
        if not taken:
            return
        items, stores = zip(*taken)
        minimums = (
            self.env[MODEL_ORDERPOINT]
            .sudo()
            .search(Domain("product_id", "in", list(set(items))) & Domain("location_id", "in", list(set(stores))))
        )
        for minimum in minimums:
            moved = taken.get((minimum.product_id.id, minimum.location_id.id))
            if moved:
                minimum._warn_if_below(moved, f"orderpoint:{minimum.id}:below:{self.ids[0]}")
