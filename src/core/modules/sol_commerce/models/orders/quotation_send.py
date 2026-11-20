from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import (
    MODEL_QUOTATION_SEND,
    MODEL_SALE_ORDER,
    MODEL_SALE_ORDER_DISCOUNT,
)
from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER
from odoo.addons.sol_commerce.constants.xml_ids import QUOTATION_REPORT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_quotation_send as QuotationSendBase
else:
    QuotationSendBase = object


# Gửi Báo Giá: the prices, discounts and payment Sales sends the customer, and to whom.
class QuotationSend(models.TransientModel, QuotationSendBase):
    _name = MODEL_QUOTATION_SEND
    _description = "Send Quotation"

    if not TYPE_CHECKING:
        # The order whose quotation is sent.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
        # The customer the quotation is for, whose contacts may receive it.
        customer_id = fields.Many2one(related="order_id.customer_id")
        # The contact the quotation is sent to.
        partner_id = fields.Many2one(related="order_id.partner_id", readonly=False, string="To")
        # The e-mail address the quotation notice goes to.
        partner_email = fields.Char(related="order_id.partner_id.email", string="E-mail")
        # The parameters and packages quoted, with their prices and discounts.
        line_ids = fields.One2many(related="order_id.product_line_ids", readonly=False)
        # The order's currency, for the totals.
        currency_id = fields.Many2one(related="order_id.currency_id")
        # The quotation's totals before tax, of tax and with tax.
        tax_totals = fields.Json(related="order_id.tax_totals")
        # Whether the quotation discount is a percentage or a fixed amount.
        discount_type = fields.Selection(
            [("percentage", "Percentage"), ("amount", "Fixed amount")],
            string="Quotation Discount",
            default="percentage",
        )
        # Percentage taken off the whole quotation as one discount line when Sales applies it.
        discount_percentage = fields.Float(string="Discount (%)")
        # Amount taken off the whole quotation as one discount line when Sales applies it.
        discount_amount = fields.Monetary(string="Discount Amount")
        # How the customer pays, how much of it in advance, and when the rest is due.
        payment_method = fields.Selection(related="order_id.payment_method", readonly=False)
        advance_mode = fields.Selection(related="order_id.advance_mode", readonly=False)
        advance_value = fields.Float(related="order_id.advance_value", readonly=False)
        balance_due = fields.Selection(related="order_id.balance_due", readonly=False)
        on_credit = fields.Boolean(related="order_id.on_credit")
        # The moment the customer has to pay the advance, or accept the quotation without one, by.
        payment_deadline = fields.Datetime(required=True)

    @api.onchange("advance_mode")
    def _onchange_advance_mode(self):
        # A percentage is never kept as an amount, nor an amount as a percentage.
        self.advance_value = 0

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id"))
        if not order or "payment_deadline" not in fields_list:
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
        return values

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "name": self.env._("Send Quotation"),
            "context": {"dialog_size": "extra-large"},
        }

    def action_apply_discount(self):
        """Take the percentage or the amount off the whole quotation as one discount line, then show the new totals."""
        self.ensure_one()
        if self.discount_type == "amount":
            if self.discount_amount <= 0 or self.discount_amount > self.order_id.amount_untaxed:
                raise UserError(self.env._("Give a discount amount above zero and at most the untaxed total."))
            values = {"discount_type": "amount", "discount_amount": self.discount_amount}
        else:
            if self.discount_percentage <= 0 or self.discount_percentage > 100:
                raise UserError(self.env._("Give a quotation discount between 0 and 100%."))
            values = {"discount_type": "so_discount", "discount_percentage": self.discount_percentage / 100}
        self.env[MODEL_SALE_ORDER_DISCOUNT].create(
            {"sale_order_id": self.order_id.id, **values}
        ).action_apply_discount()
        self.write({"discount_percentage": 0, "discount_amount": 0})
        return self._reopen()

    def action_preview(self):
        """The quotation PDF as the customer would receive it now."""
        self.ensure_one()
        return self.env.ref(QUOTATION_REPORT).report_action(self.order_id)

    def action_send(self):
        self.ensure_one()
        if self.payment_deadline <= fields.Datetime.now():
            raise UserError(self.env._("Give a payment deadline that is still to come."))
        self.order_id.payment_deadline = self.payment_deadline
        return self.order_id.action_send_quotation()
