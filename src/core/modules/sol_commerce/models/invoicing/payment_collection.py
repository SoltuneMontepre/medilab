from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_PAYMENT_COLLECTION, MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_payment_collection as PaymentCollectionBase
else:
    PaymentCollectionBase = object


# Ghi nhận khoản thanh toán
class PaymentCollection(models.TransientModel, PaymentCollectionBase):
    _name = MODEL_PAYMENT_COLLECTION
    _description = "Record Payment"

    if not TYPE_CHECKING:
        # Order for which Sales received the funds.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, readonly=True)
        # Currency of the order.
        currency_id = fields.Many2one(related="order_id.currency_id")
        # Summary of the quotation and its active payment request.
        customer_id = fields.Many2one(related="order_id.customer_id")
        order_total = fields.Monetary(related="order_id.amount_total", string="Quotation Total")
        payment_request_id = fields.Many2one(related="order_id.payment_request_id")
        request_kind = fields.Selection(related="payment_request_id.kind", string="Request")
        request_amount = fields.Monetary(related="payment_request_id.amount", string="Requested Amount")
        verified_amount = fields.Monetary(related="payment_request_id.verified_amount", string="Paid Amount")
        remaining_amount = fields.Monetary(related="payment_request_id.remaining_amount", string="Remaining Due")
        deadline = fields.Datetime(related="payment_request_id.deadline", string="Payment Deadline")
        # How much the customer paid.
        amount = fields.Monetary(required=True)
        # How Sales received the money.
        method = fields.Selection([("cash", "Cash"), ("bank_transfer", "Bank transfer")], required=True)
        # When Sales received the funds.
        received_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # The original bank or cash reference.
        reference = fields.Char()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id") or self.env.context.get("default_order_id"))
        if not order:
            return values
        if "amount" in fields_list and not values.get("amount"):
            values["amount"] = order.payment_request_id.remaining_amount or order.amount_total
        if "method" in fields_list and not values.get("method") and order.payment_method in ("cash", "bank_transfer"):
            values["method"] = order.payment_method
        return values

    def action_record(self):
        self.ensure_one()
        self.order_id.action_record_collection(self.amount, self.method, self.received_at, self.reference)
        return {"type": "ir.actions.act_window_close"}
