from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_PAYMENT_REQUEST,
    MODEL_QUOTATION,
    MODEL_QUOTATION_SAMPLING,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_commerce.constants.orders import (
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
from odoo.addons.sol_laboratory.services.staff_language import staff_env

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
    _audit_children = ("sampling_ids",)

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
        # Payment requests tied to this quotation revision.
        payment_request_ids = fields.One2many(MODEL_PAYMENT_REQUEST, "quotation_id")
        # Posted advance invoice of a quotation issued before payment requests.
        advance_invoice_id = fields.Many2one(
            MODEL_ACCOUNT_MOVE, ondelete="restrict", copy=False, index="btree_not_null", readonly=True
        )
        # Reference of the customer's email or written agreement recorded by Sales.
        agreement_reference = fields.Char(readonly=True, copy=False)
        # The PDF sent to the customer.
        attachment_id = fields.Many2one("ir.attachment", required=True, ondelete="restrict")
        # The expected samples, containers and amounts sent with the quotation; accepting it makes them the order's.
        sampling_ids = fields.One2many(MODEL_QUOTATION_SAMPLING, "quotation_id", string="Expected Sampling")

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
        """Accept the quotation when it takes no further payment."""
        self.ensure_one()
        user = self.env.user
        order = self.order_id.sudo()
        if not (user.share and order._owned_by(user)):
            raise AccessError(self.env._("Only the customer of the order can accept its quotation."))
        order._lock_payment_orders()
        self._check_explicit_acceptance()
        self._accept()
        return True

    def _check_explicit_acceptance(self):
        self.ensure_one()
        order = self.order_id.sudo()
        if self != order._latest_quotation() or self.status != QUOTATION_SENT or order.state == "cancel":
            raise UserError(self.env._("Only a quotation that was sent can be accepted."))
        if order.state == "draft":
            raise UserError(self.env._("This quotation is being revised."))
        if order.payment_deadline and order.payment_deadline < fields.Datetime.now():
            raise UserError(self.env._("This quotation has expired."))
        if order.payment_request_id.amount or self.sudo().advance_invoice_id:
            raise UserError(self.env._("Pay the requested advance to accept this quotation."))

    def _accept(self):
        self.sudo().write({"status": QUOTATION_ACCEPTED})
        self.order_id.sudo().write({"accepted_at": fields.Datetime.now()})

    def _accept_payment(self):
        self.ensure_one()
        order = self.order_id.sudo()
        if (
            self.status in (QUOTATION_SENT, QUOTATION_EXPIRED)
            and order.state == "sent"
            and self == order._latest_quotation()
        ):
            self._accept()

    def action_decline(self, reason):
        """The customer declines the quotation with a reason; the order stays as it is."""
        self.ensure_one()
        text = (reason or "").strip()
        if not text:
            raise UserError(self.env._("Give a reason for declining the quotation."))
        order = self.order_id.sudo()
        order._lock_payment_orders()
        order._check_no_pending_collection()
        if self.status != QUOTATION_SENT:
            raise UserError(self.env._("Only a quotation that was sent can be declined."))
        order.payment_request_id._supersede()
        self.sudo().write({"status": QUOTATION_DECLINED, "decline_reason": text})
        self._notify_declined(text)
        return True

    def _notify_declined(self, reason):
        self.ensure_one()
        order = self.order_id.sudo()
        # The note is for the salesperson, in their language, not the customer's.
        env = staff_env(self.env, order.user_id)
        order.message_post(
            body=env._("The customer declined quotation %(code)s: %(reason)s", code=self.code, reason=reason),
            partner_ids=order.user_id.partner_id.ids,
            subtype_xmlid="mail.mt_comment",
        )

    @api.model
    def _flag_expired(self):
        """Mark sent quotations past the order's payment deadline as expired; the order is not cancelled."""
        late = self.sudo().search(
            [("status", "=", QUOTATION_SENT), ("order_id.payment_deadline", "<", fields.Datetime.now())]
        )
        late.order_id._lock_payment_orders()
        now = fields.Datetime.now()
        late.filtered(
            lambda item: (
                item.status == QUOTATION_SENT
                and item.order_id.payment_deadline
                and item.order_id.payment_deadline < now
            )
        ).write({"status": QUOTATION_EXPIRED})
        self.env[MODEL_PAYMENT_REQUEST]._expire_requests()
