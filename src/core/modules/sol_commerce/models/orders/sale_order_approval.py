from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    APPROVAL_APPROVED,
    APPROVAL_NONE,
    APPROVAL_REJECTED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_APPROVAL_MIXIN, MODEL_PERSON

# What the customer and sales agreed: edits stop once a signature stands.
APPROVAL_CONTENT_FIELDS = frozenset({"customer_id", "partner_id", "payment_deadline", "validity_date"})


# Đơn Hàng: the order is approved by signatures.
class SaleOrderApproval(models.Model):
    _name = MODEL_SALE_ORDER
    _inherit = [MODEL_SALE_ORDER, MODEL_APPROVAL_MIXIN]
    _audit_children = ("order_line", "quotation_ids", "sample_ids", "cancellation_request_ids", "support_request_ids")

    def action_request_approval(self):
        """Sign the first level, which asks the next levels to approve the confirmed order, again after a rejection."""
        self.ensure_one()
        if self.approval_status not in (APPROVAL_NONE, APPROVAL_REJECTED):
            raise UserError(self.env._("The approval of this order was already requested."))
        return self.action_sign()

    def action_reject(self, reason):
        """A rejection ends the round: its signatures and the rejection stay on record, set aside, so sales corrects
        the order and requests approval again from the first level."""
        result = super().action_reject(reason)
        order = self.sudo()
        order._approval_restart()
        order._approval_set_state(APPROVAL_REJECTED)
        return result

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
