from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER
from odoo.addons.sol_inventory.constants.stock import CANCELLED, DONE, ORDER_DRAFT, ORDER_SENT
from odoo.addons.sol_laboratory.constants.approvals import (
    APPROVAL_SYSTEM_CONTEXT,
    STATE_APPROVED,
    STATE_NONE,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_MIXIN, MODEL_PERSON

if TYPE_CHECKING:
    from medilab_model_types import Model_purchase_order as PurchaseOrderApprovalBase
else:
    PurchaseOrderApprovalBase = object

# What the signers approved: edits stop once a signature stands.
APPROVAL_CONTENT_FIELDS = frozenset({"partner_id", "department_id", "order_line", "currency_id", "picking_type_id"})


# Đơn Mua Hàng: the order is signed through its approval chain before it is sent.
class PurchaseOrderApproval(models.Model, PurchaseOrderApprovalBase):
    _name = MODEL_PURCHASE_ORDER
    _inherit = [MODEL_PURCHASE_ORDER, MODEL_APPROVAL_MIXIN]
    _audit_children = ("order_line",)

    def action_request_approval(self):
        """Sign the first level, which asks the next levels to sign the order."""
        self.ensure_one()
        if self.approval_status != STATE_NONE:
            raise UserError(self.env._("The approval of this order was already requested."))
        return self.action_sign()

    def action_sign(self):
        self.ensure_one()
        if self.state != ORDER_DRAFT:
            raise UserError(self.env._("Only an order that is not sent yet can be signed."))
        if not self.order_line.filtered(lambda line: not line.display_type):
            raise UserError(self.env._("An order without items cannot be signed."))
        if not self.department_id:
            raise UserError(self.env._("Name the department that asked for the order before it is signed."))
        return super().action_sign()

    def action_send_to_supplier(self):
        """Confirm the signed order, which makes its receipt, and open the email that sends it to the supplier."""
        self.ensure_one()
        self._check_signed()
        self.check_access("write")
        self._check_permission("edit")
        self.sudo().button_confirm()
        return self.with_context(send_rfq=False).action_rfq_send()

    def button_approve(self, force=False):
        self._unsent()._check_signed()
        return super().button_approve(force=force)

    def action_rfq_send(self):
        # Sending an order before its chain signed it is refused; a sent order can be sent again.
        self._unsent()._check_signed()
        return super().action_rfq_send()

    def _mark_rfqs_as_sent(self):
        # An order is a draft until it is sent to the supplier, which confirms it; MediLab has no quotation request.
        return None

    def button_cancel(self):
        for order in self:
            if order.state == ORDER_DRAFT and order._approval_has_standing():
                raise UserError(
                    self.env._("%s has signatures; withdraw them before cancelling the order.", order.display_name)
                )
            if DONE in order.picking_ids.mapped("state"):
                raise UserError(
                    self.env._("%s cannot be cancelled once goods were received for it.", order.display_name)
                )
        return super().button_cancel()

    def button_draft(self):
        for order in self:
            if order._approval_has_standing():
                raise UserError(
                    self.env._(
                        "%s was signed, so it cannot be reopened; duplicate it to order again.", order.display_name
                    )
                )
        return super().button_draft()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        signed = self.filtered(lambda order: order._approval_has_standing())
        if signed:
            raise UserError(
                self.env._(
                    "Signed purchase orders are cancelled, never deleted: %s",
                    format_list(self.env, signed.mapped("display_name")),
                )
            )

    def _unsent(self):
        return self.filtered(lambda order: order.state not in (ORDER_SENT, CANCELLED))

    def _check_signed(self):
        for order in self:
            if order.approval_status != STATE_APPROVED:
                raise UserError(
                    self.env._("%s cannot be sent before its approval chain has signed it.", order.display_name)
                )

    def _check_unsigned(self):
        """Refuse changing what the signers approved while a signature stands."""
        if not self.env.context.get(APPROVAL_SYSTEM_CONTEXT) and self._approval_has_standing():
            raise UserError(self.env._("The order has signatures; withdraw them before changing it."))

    def _approval_requester(self):
        self.ensure_one()
        return self.env[MODEL_PERSON].sudo().search([("user_id", "=", self.user_id.id)], limit=1)

    def _approval_department(self):
        self.ensure_one()
        return self.department_id

    def _approval_content_fields(self):
        return APPROVAL_CONTENT_FIELDS

    def _approval_process_completed(self):
        return self.state in (ORDER_SENT, CANCELLED)

    def _approval_set_state(self, state):
        self.write({"approval_status": state})

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        self.sudo().message_post(
            body=self.env._("The approval of this order was rejected: %s", reason),
            partner_ids=self.user_id.partner_id.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
