from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.approvals import STATE_REQUESTED
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_MIXIN, MODEL_PERSON

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderApprovalBase
else:
    SaleOrderApprovalBase = object

# What the customer and sales agreed: edits stop once a signature stands.
APPROVAL_CONTENT_FIELDS = frozenset({"customer_id", "partner_id", "payment_deadline", "validity_date"})


# Đơn Hàng: the order is approved by signatures.
class SaleOrderApproval(models.Model, SaleOrderApprovalBase):
    _name = MODEL_SALE_ORDER
    _inherit = [MODEL_SALE_ORDER, MODEL_APPROVAL_MIXIN]
    _audit_children = ("order_line", "quotation_ids", "sample_ids", "cancellation_request_ids", "support_request_ids")

    if not TYPE_CHECKING:
        # The role whose signature a requested approval waits for; empty when no approval is requested.
        approval_waiting_for = fields.Char(
            string="Waiting for", compute="_compute_approval_waiting_for", compute_sudo=True
        )

    @api.depends("approval_status")
    def _compute_approval_waiting_for(self):
        for order in self:
            level = order._approval_waiting_level() if order.approval_status == STATE_REQUESTED else False
            order.approval_waiting_for = level.role_id.name if level else False

    def _approval_waiting_level(self):
        self.ensure_one()
        chain = self._approval_chain()
        return self._approval_next_level(chain, self._approval_open_rows()) if chain else False

    def action_request_approval(self):
        """Sign the first level, which asks the next levels to approve the confirmed order."""
        self.ensure_one()
        if self.approval_status != APPROVAL_NONE:
            raise UserError(self.env._("The approval of this order was already requested."))
        return self.action_sign()

    def action_sign(self):
        self.ensure_one()
        if self.order_status != STATUS_CONFIRMED:
            raise UserError(self.env._("Only a confirmed order can be signed."))
        return super().action_sign()

    def action_start_sample_collection(self):
        """Refuse until the approval is signed; the collection itself is not part of the order."""
        for order in self:
            if order.approval_status != APPROVAL_APPROVED:
                raise UserError(self.env._("The order must be approved before the samples are collected."))
        return True

    def _approval_check_actor(self, rejecting=False):
        """Signing or rejecting changes the order, so a salesperson who may only read it cannot act on it."""
        if not self._can_edit():
            raise AccessError(self.env._("You may only read this order, so you cannot sign or reject it."))
        return super()._approval_check_actor(rejecting)

    def _approval_requester(self):
        self.ensure_one()
        return self.env[MODEL_PERSON].sudo().search([("user_id", "=", self.user_id.id)], limit=1)

    def _approval_content_fields(self):
        return APPROVAL_CONTENT_FIELDS

    def _approval_process_completed(self):
        return self.order_status == STATUS_COMPLETED

    def _approval_set_state(self, state):
        self.write(
            {"approval_status": state, "approved_at": fields.Datetime.now() if state == APPROVAL_APPROVED else False}
        )

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        self.sudo().message_post(
            body=self.env._("The approval of this order was rejected: %s", reason),
            partner_ids=self.user_id.partner_id.ids,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
