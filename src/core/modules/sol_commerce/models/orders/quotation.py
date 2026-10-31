from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.api import SUPERUSER_ID
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_QUOTATION, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_TOUCHED_STATES,
    QUOTATION_ACCEPTED,
    QUOTATION_DECLINED,
    QUOTATION_EXPIRED,
    QUOTATION_REPLACED,
    QUOTATION_SENT,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_quotation as QuotationBase
else:
    QuotationBase = object


# Báo Giá
class Quotation(models.Model, QuotationBase):
    _name = MODEL_QUOTATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Quotation"
    _order = "order_id desc, revision desc"
    _rec_name = "code"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # Unique quotation number in the format the administrator configures, such as 0001 26/BG-VTT; filled from a sequence.
        code = fields.Char(required=True, copy=False, readonly=True)
        # The order quoted.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="restrict")
        # Revision number, 1 for the first quotation of the order.
        revision = fields.Integer(required=True, default=1)
        # The revision this one replaces; empty for revision 1.
        replaces_id = fields.Many2one(MODEL_QUOTATION, ondelete="restrict", copy=False)
        # sent, accepted, declined, expired or replaced.
        status = fields.Selection(
            [
                (QUOTATION_SENT, "Sent"),
                (QUOTATION_ACCEPTED, "Accepted"),
                (QUOTATION_DECLINED, "Declined"),
                (QUOTATION_EXPIRED, "Expired"),
                (QUOTATION_REPLACED, "Replaced"),
            ],
            required=True,
            default=QUOTATION_SENT,
            index=True,
        )
        # When the quotation was sent.
        sent_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # The currency of the order.
        currency_id = fields.Many2one(related="order_id.currency_id")
        # Total including VAT, as sent.
        amount_total = fields.Monetary(required=True)
        # The customer's reason for declining.
        decline_reason = fields.Text()
        # The advance invoice sent with the quotation; empty when it was sent without an advance.
        advance_invoice_id = fields.Many2one(
            MODEL_ACCOUNT_MOVE, ondelete="restrict", copy=False, index="btree_not_null"
        )
        # The PDF sent to the customer.
        attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="restrict")

    _code_unique = models.Constraint("UNIQUE(code)", "The number of a quotation must be unique.")
    _revision_unique = models.Constraint(
        "UNIQUE(order_id, revision)", "An order has only one quotation for each revision."
    )
    _replaces_unique = models.Constraint("UNIQUE(replaces_id)", "A revision can be replaced only once.")

    def write(self, vals):
        if self.filtered(lambda quotation: quotation.status == QUOTATION_REPLACED):
            raise UserError(self.env._("A replaced quotation cannot be changed."))
        return super().write(vals)

    def action_send(self):
        """Send the order's next revision; a replaced quotation is never sent again."""
        for quotation in self:
            if quotation.status == QUOTATION_REPLACED:
                raise UserError(self.env._("A replaced quotation cannot be sent. Send the current revision instead."))
        return self.order_id.action_send_quotation()

    def action_accept(self):
        """The customer accepts a quotation sent without an advance; with an advance, paying it accepts."""
        self.ensure_one()
        user = self.env.user
        order = self.order_id.sudo()
        if not (user.share and order._owned_by(user)):
            raise AccessError(self.env._("Only the customer of the order can accept its quotation."))
        if self.sudo().advance_invoice_id:
            raise UserError(self.env._("Pay the advance invoice to accept this quotation."))
        if self.status != QUOTATION_SENT:
            raise UserError(self.env._("Only a quotation that was sent can be accepted."))
        if order.state == "draft":
            raise UserError(self.env._("This quotation is being revised."))
        self._accept()
        return True

    def _accept(self):
        """Accept the quotations that are still sent, whether the customer or the payment of the advance did it."""
        accepted = self.sudo().filtered(
            lambda quotation: quotation.status == QUOTATION_SENT and quotation.order_id.state != "draft"
        )
        accepted.write({"status": QUOTATION_ACCEPTED})
        accepted.order_id.write({"accepted_at": fields.Datetime.now()})

    def _is_advance_touched(self):
        """True when the customer has paid, or started paying, the advance invoice."""
        self.ensure_one()
        return self.sudo().advance_invoice_id.payment_state in ADVANCE_TOUCHED_STATES

    def _cancel_advance_invoice(self):
        """Cancel the advance invoice nobody paid, so a replaced quotation cannot be paid and only the new one can."""
        for invoice in self.sudo().advance_invoice_id.with_user(SUPERUSER_ID):
            if invoice.state == "cancel" or invoice.payment_state in ADVANCE_TOUCHED_STATES:
                continue
            if invoice.state == "posted":
                invoice.with_context(medilab_cancel_unpaid_advance=True).button_draft()
            invoice.button_cancel()

    def action_decline(self, reason):
        """The customer declines the quotation with a reason; the order stays as it is."""
        self.ensure_one()
        text = (reason or "").strip()
        if not text:
            raise UserError(self.env._("Give a reason for declining the quotation."))
        if self.status != QUOTATION_SENT:
            raise UserError(self.env._("Only a quotation that was sent can be declined."))
        self.sudo().write({"status": QUOTATION_DECLINED, "decline_reason": text})
        self._notify_declined(text)
        return True

    def _notify_declined(self, reason):
        self.ensure_one()
        order = self.order_id.sudo()
        order.message_post(
            body=self.env._("The customer declined quotation %(code)s: %(reason)s", code=self.code, reason=reason),
            partner_ids=order.user_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )

    @api.model
    def _flag_expired(self):
        """Mark sent quotations past the order's payment deadline as expired; the order is not cancelled."""
        late = self.sudo().search(
            [("status", "=", QUOTATION_SENT), ("order_id.payment_deadline", "<", fields.Datetime.now())]
        )
        late.write({"status": QUOTATION_EXPIRED})
