from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_PAYMENT,
    MODEL_PAYMENT_REQUEST,
    MODEL_PAYMENT_TRANSACTION,
    MODEL_QUOTATION,
    MODEL_SALE_ORDER,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_payment_request as PaymentRequestBase
else:
    PaymentRequestBase = object


# Yêu Cầu Thanh Toán
class PaymentRequest(models.Model, PaymentRequestBase):
    _name = MODEL_PAYMENT_REQUEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Payment Request"
    _order = "id desc"
    _rec_name = "quotation_id"
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # Order to which the requested funds belong.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="restrict", index=True, readonly=True)
        # Quotation version on which this request is based.
        quotation_id = fields.Many2one(MODEL_QUOTATION, required=True, ondelete="restrict", index=True, readonly=True)
        # Currency of the order.
        currency_id = fields.Many2one(related="order_id.currency_id")
        # Company collecting the money.
        company_id = fields.Many2one(related="order_id.company_id")
        # Contact who receives the request.
        partner_id = fields.Many2one(related="order_id.partner_id")
        # Whether the request collects the advance or the confirmed order's balance.
        kind = fields.Selection([("advance", "Advance"), ("balance", "Balance")], required=True, readonly=True)
        # How the customer pays the request: the order's payment method when it was made.
        advance_method = fields.Selection(
            [("online", "Online"), ("bank_transfer", "Bank transfer"), ("cash", "Cash")], readonly=True
        )
        # Total requested from the customer after deducting funds already on the order.
        amount = fields.Monetary(required=True, readonly=True)
        # Verified funds from earlier requests used to calculate this request's amount.
        carried_amount = fields.Monetary(readonly=True)
        # Verified money received against this request.
        verified_amount = fields.Monetary(compute="_compute_amounts", compute_sudo=True)
        # Cash and bank transfers waiting for the accountant.
        pending_amount = fields.Monetary(compute="_compute_amounts", compute_sudo=True)
        # Amount the customer still needs to pay.
        remaining_amount = fields.Monetary(compute="_compute_amounts", compute_sudo=True)
        # Latest time a payment can be received toward the advance.
        deadline = fields.Datetime(index=True)
        # The stage of the request. Expiry leaves its payments on the order.
        state = fields.Selection(
            [("open", "Open"), ("funded", "Funded"), ("expired", "Expired"), ("superseded", "Superseded")],
            required=True,
            default="open",
            index=True,
            readonly=True,
        )
        # Payments applied to the request or awaiting verification.
        payment_ids = fields.One2many(MODEL_ACCOUNT_PAYMENT, "payment_request_id")
        # PayOS links and bank transfers originating with this request.
        transaction_ids = fields.One2many(MODEL_PAYMENT_TRANSACTION, "payment_request_id")

    _per_quotation_kind = models.Constraint("UNIQUE(quotation_id, kind)", "A quotation has one request of each kind.")

    @api.constrains("kind", "deadline")
    def _check_balance_deadline(self):
        if any(request.kind == "balance" and request.deadline for request in self):
            raise ValidationError(self.env._("Balance payment requests have no deadline."))

    @api.depends("amount", "payment_ids.amount", "payment_ids.state", "payment_ids.reviewed_at")
    def _compute_amounts(self):
        for request in self:
            payments = request.payment_ids
            request.verified_amount = sum(payments.filtered(lambda item: item._verified_for_request()).mapped("amount"))
            request.pending_amount = sum(
                payments.filtered(lambda item: item._pending_manual_collection()).mapped("amount")
            )
            request.remaining_amount = max(request.currency_id.round(request.amount - request.verified_amount), 0)

    def _takes_payments(self):
        self.ensure_one()
        return bool(
            self.state == "open"
            and self.order_id.payment_request_id == self
            and self.order_id.state != "cancel"
            and (not self.deadline or self.deadline >= fields.Datetime.now())
            and (self.kind == "balance" or self.quotation_id.status == "sent")
            and self.order_id.state != "draft"
        )

    def _check_takes_payments(self):
        if not self._takes_payments():
            raise UserError(self.env._("This payment request no longer takes new payments."))

    def _refresh_funding(self):
        self.ensure_one()
        if self.state == "superseded" or self.remaining_amount:
            return
        self.state = "funded"
        self._close_payos_links()
        if self.kind == "advance" and self.amount:
            self.quotation_id._accept_payment()
        self.order_id._release_test_request()

    def _close_payos_links(self):
        self.sudo().transaction_ids._payos_close_request_links()

    def _supersede(self):
        self.write({"state": "superseded"})
        self._close_payos_links()

    @api.model
    def _expire_requests(self):
        now = fields.Datetime.now()
        due = self.sudo().search([("state", "=", "open"), ("deadline", "<", now)])
        due.order_id._lock_payment_orders()
        due = due.filtered(lambda request: request.state == "open" and request.deadline and request.deadline < now)
        due.write({"state": "expired"})
        due._close_payos_links()
