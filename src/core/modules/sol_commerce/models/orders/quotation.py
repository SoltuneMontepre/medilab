from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    QUOTATION_ACCEPTED,
    QUOTATION_DECLINED,
    QUOTATION_EXPIRED,
    QUOTATION_REPLACED,
    QUOTATION_SENT,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_CODE_MIXIN, MODEL_PERMISSION_MIXIN


# Báo Giá
class Quotation(models.Model):
    _name = MODEL_QUOTATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN]
    _description = "Quotation"
    _order = "order_id desc, revision desc"
    _rec_name = "code"
    _permission_actions = ("read", "create", "edit", "delete")

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
