from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION_SEND, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_quotation_send as QuotationSendBase
else:
    QuotationSendBase = object


# Gửi Báo Giá: what Sales agrees with the customer when sending the quotation.
class QuotationSend(models.TransientModel, QuotationSendBase):
    _name = MODEL_QUOTATION_SEND
    _description = "Send Quotation"

    if not TYPE_CHECKING:
        # The order whose quotation is sent.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
        # The moment the customer has to pay the advance, or accept the quotation without one, by.
        payment_deadline = fields.Datetime(required=True)
        # The day agreed with the customer for the samples to be picked up.
        expected_collection_date = fields.Date(string="Expected Sample Pickup", required=True)
        # The return date samples picked up on that day give, after the work the laboratory holds.
        estimated_result_date = fields.Date(string="Estimated Return Date", compute="_compute_estimated_result_date")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id"))
        if not order:
            return values
        now = fields.Datetime.now()
        deadline = order.payment_deadline
        if not deadline or deadline <= now:
            days = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_int(PAYMENT_DEADLINE_PARAMETER, DEFAULT_PAYMENT_DEADLINE_DAYS)
            )
            deadline = now + timedelta(days=days)
        latest = order._latest_payment_deadline()
        values.setdefault("payment_deadline", min(deadline, latest) if latest else deadline)
        if order.expected_collection_date and order.expected_collection_date >= fields.Date.context_today(self):
            values.setdefault("expected_collection_date", order.expected_collection_date)
        return values

    @api.depends("order_id", "expected_collection_date")
    def _compute_estimated_result_date(self):
        for wizard in self:
            order = wizard.order_id
            wizard.estimated_result_date = bool(order) and order._earliest_return_date(wizard.expected_collection_date)

    def action_send(self):
        self.ensure_one()
        if self.expected_collection_date < fields.Date.context_today(self):
            raise UserError(self.env._("Agree a sample pickup day that is still to come."))
        if self.payment_deadline <= fields.Datetime.now():
            raise UserError(self.env._("Give a payment deadline that is still to come."))
        self.order_id.write(
            {"payment_deadline": self.payment_deadline, "expected_collection_date": self.expected_collection_date}
        )
        return self.order_id.action_send_quotation()
