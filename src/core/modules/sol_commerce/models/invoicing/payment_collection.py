from typing import TYPE_CHECKING

from odoo import fields, models

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
        # How much the customer paid.
        amount = fields.Monetary(required=True)
        # How Sales received the money.
        method = fields.Selection([("cash", "Cash"), ("bank_transfer", "Bank transfer")], required=True)
        # When Sales received the funds.
        received_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # The original bank or cash reference.
        reference = fields.Char()

    def action_record(self):
        self.ensure_one()
        self.order_id.action_record_collection(self.amount, self.method, self.received_at, self.reference)
        return {"type": "ir.actions.act_window_close"}
