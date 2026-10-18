from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_PREPARATION,
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import (
    DONE,
    LOT_AVAILABLE,
    MOVE_CONSUMPTION,
    MOVE_PREPARATION,
    MOVE_RECEIPT,
    MOVE_WASTE,
    RECEIPT_CODE,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TEST_RESULT,
)

# A done move keeps the locations given here; Odoo would clear a destination that has no transfer.
KEEP_SRC = "medilab_keep_location_src"
KEEP_DEST = "medilab_keep_location_dest"
# What a done move recorded. A mistake is corrected by another move.
DONE_MOVE_FIELDS = frozenset(
    {"product_id", "product_uom_qty", "quantity", "location_id", "location_dest_id", "move_line_ids"}
)


# Phiếu Xuất Kho
class StockMove(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_MOVE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN, MODEL_STOCK_MOVE]
    # Reading and recording a use or a waste. There is no edit permission: a done move is never changed.
    _permission_actions = ("read", "create")

    # receipt, preparation, consumption or waste, from what the move itself does.
    move_kind = fields.Selection(
        [
            (MOVE_RECEIPT, "Receipt"),
            (MOVE_PREPARATION, "Preparation"),
            (MOVE_CONSUMPTION, "Consumption"),
            (MOVE_WASTE, "Waste"),
        ],
        string="Kind",
        compute="_compute_move_kind",
        store=True,
        precompute=True,
        readonly=False,
        required=True,
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
        "preparation_id",
        "location_dest_id.usage",
        "picking_id.picking_type_id.code",
        "purchase_line_id",
    )
    def _compute_move_kind(self):
        for move in self:
            move.move_kind = move._kind()

    def _kind(self):
        self.ensure_one()
        if self.is_scrap:
            return MOVE_WASTE
        if self.preparation_id:
            return MOVE_PREPARATION
        if self.location_dest_id.usage == "production":
            return MOVE_CONSUMPTION
        picking = self.picking_id
        if self.purchase_line_id or (picking and picking.picking_type_id.code == RECEIPT_CODE):
            return MOVE_RECEIPT
        # Kinds added later replace this. A required kind cannot be empty on moves that already exist.
        return MOVE_RECEIPT

    def _compute_location_id(self):
        src_id = self.env.context.get(KEEP_SRC)
        if not src_id:
            return super()._compute_location_id()
        manual = self.filtered(lambda move: not move.picking_id)
        for move in manual:
            move.location_id = src_id
        if rest := self - manual:
            super(StockMove, rest)._compute_location_id()
        return None

    def _compute_location_dest_id(self):
        dest_id = self.env.context.get(KEEP_DEST)
        if not dest_id:
            return super()._compute_location_dest_id()
        manual = self.filtered(lambda move: not move.picking_id and not move.is_scrap)
        for move in manual:
            move.location_dest_id = dest_id
        if rest := self - manual:
            super(StockMove, rest)._compute_location_dest_id()
        return None

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
        self.filtered(lambda move: move.state == DONE)._settle_containers()
        return done

    def _settle_containers(self):
        for move in self:
            move.move_line_ids.package_id._settle(move.is_scrap)

    def _take_containers(self, item, containers, quantity, *, scrap=False, allow_sealed=False, person=None, **vals):
        """Use or waste quantity of item from these containers, in order, and finish the moves."""
        if not allow_sealed:
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
        context = {KEEP_SRC: location.id}
        if not scrap:
            context[KEEP_DEST] = dest.id
        move = self.sudo().with_context(**context).create(create_vals)
        finished = move.with_context(**{KEEP_SRC: False, KEEP_DEST: False})
        if scrap:
            finished._action_scrap()
        else:
            finished.picked = True
            finished.move_line_ids.picked = True
            finished._action_done()
        return move

    @api.model
    def _amount(self, item, quantity):
        return item.uom_id.round(quantity)
