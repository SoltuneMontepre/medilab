from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_PACKAGE, MODEL_STOCK_PICKING
from odoo.addons.sol_inventory.constants.stock import DONE, RECEIPT_CODE
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Phiếu Nhập Kho
class StockPicking(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_PICKING
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_PICKING, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("read", "create", "edit", "delete")
    _audit_children = ("move_line_ids",)

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
        receipts.move_line_ids._check_expiry_typed()
        receipts.move_line_ids._put_in_containers()
        # A receipt keeps what did not arrive as a backorder, so its purchase order stays partially received.
        super(StockPicking, receipts.with_context(cancel_backorder=False))._action_done()
        super(StockPicking, self - receipts)._action_done()
        receipts.move_line_ids._attach_certificates()
        return True

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
