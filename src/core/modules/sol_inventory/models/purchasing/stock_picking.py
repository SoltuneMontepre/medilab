from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_PACKAGE, MODEL_STOCK_PICKING, MODEL_SUPPLIER_INFO
from odoo.addons.sol_inventory.constants.stock import CANCELLED, DONE, RECEIPT_CODE
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_stock_picking as StockPickingBase
else:
    StockPickingBase = object


# Phiếu Nhập Kho
class StockPicking(models.Model, StockPickingBase):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_PICKING
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_PICKING, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("read", "create", "edit", "delete")
    _audit_children = ("move_line_ids",)

    if not TYPE_CHECKING:
        # The containers the receipt put its bottles and vials in.
        container_ids = fields.Many2many(MODEL_STOCK_PACKAGE, string="Containers", compute="_compute_container_ids")
        # How many containers the receipt made.
        container_count = fields.Integer(string="Container Count", compute="_compute_container_ids")

    @api.depends("move_line_ids.result_package_id")
    def _compute_container_ids(self):
        for picking in self:
            picking.container_ids = picking.move_line_ids.result_package_id
            picking.container_count = len(picking.container_ids)

    @api.constrains("location_dest_id", "picking_type_id")
    def _check_receipt_destination(self):
        self._receipts().location_dest_id._check_in_central_store()

    def button_validate(self):
        if self.env.su or not self or self._receipts() != self:
            return super().button_validate()
        # Validating makes lots, containers, quants and moves, which only Odoo's stock users may write.
        self.check_access("write")
        self._check_permission("edit")
        return super(StockPicking, self.sudo()).button_validate()

    def _action_done(self):
        receipts = self._receipts()
        receipts._check_ordered_items()
        # Only picked lines arrive now; Odoo moves the others to the backorder.
        arrived = receipts.move_line_ids.filtered("picked")
        arrived._check_expiry_typed()
        arrived._put_in_containers()
        # A receipt keeps what did not arrive as a backorder, so its purchase order stays partially received.
        super(StockPicking, receipts.with_context(cancel_backorder=False))._action_done()
        super(StockPicking, self - receipts)._action_done()
        receipts.move_line_ids._attach_certificates()
        receipts._record_supplier_prices()
        return True

    def _check_ordered_items(self):
        """Refuse receiving against a purchase order an item the order does not list: Odoo would add it to the order,
        which stays as its signers signed it."""
        for receipt in self.filtered("purchase_id"):
            extra = receipt._moves_off_order()
            if extra:
                raise UserError(
                    self.env._(
                        "%(order)s does not list %(items)s; receive them on a receipt without a purchase order.",
                        order=receipt.purchase_id.display_name,
                        items=format_list(self.env, extra.product_id.mapped("display_name")),
                    )
                )

    def _moves_off_order(self):
        """The picked moves of the receipt whose item its purchase order does not list."""
        self.ensure_one()
        ordered = self.purchase_id.order_line.product_id
        return self.move_ids.filtered(
            lambda move: (
                move.picked
                and move.state not in (DONE, CANCELLED)
                and not move.purchase_line_id
                and move.product_id not in ordered
            )
        )

    def _record_supplier_prices(self):
        """Keep what each received item cost as its supplier's last price for it; an item received without a price
        leaves the last price as it was."""
        supplier_items = self.env[MODEL_SUPPLIER_INFO]
        for receipt in self:
            supplier = receipt.partner_id.commercial_partner_id
            if not supplier.sudo().with_context(active_test=False).supplier_ids:
                continue
            currency = receipt.company_id.currency_id
            for move in receipt.move_ids.filtered(
                lambda move: bool(
                    move.state == DONE and move.product_id.item_kind and not currency.is_zero(move.price_unit)
                )
            ):
                supplier_items._record_last_price(supplier, move.product_id, move.price_unit)

    def _check_backorder(self):
        return super(StockPicking, self - self._receipts())._check_backorder()

    def action_toggle_is_locked(self):
        if self.filtered(lambda picking: picking.state == DONE and picking.is_locked):
            raise UserError(self.env._("Done moves are never changed; correct a mistake with another move."))
        return super().action_toggle_is_locked()

    def action_open_containers(self):
        return self.container_ids._action_open()

    def action_print_container_labels(self):
        return self.env.ref(CONTAINER_LABEL_REPORT).report_action(self.container_ids)

    def action_print_small_container_labels(self):
        return self.env.ref(SMALL_CONTAINER_LABEL_REPORT).report_action(self.container_ids)

    def _receipts(self):
        return self.filtered(lambda picking: picking.picking_type_code == RECEIPT_CODE)
