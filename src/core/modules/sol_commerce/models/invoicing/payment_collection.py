from typing import TYPE_CHECKING

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools import format_datetime

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
        # Read-only summary of the quotation and its active payment request shown beside the payment fields.
        summary_html = fields.Html(compute="_compute_summary_html", sanitize=False)
        # How much the customer paid.
        amount = fields.Monetary(required=True)
        # How Sales received the money.
        method = fields.Selection([("cash", "Cash"), ("bank_transfer", "Bank transfer")], required=True)
        # When Sales received the funds.
        received_at = fields.Datetime(required=True, default=fields.Datetime.now)
        # The original bank or cash reference.
        reference = fields.Char()

    @api.depends("order_id")
    def _compute_summary_html(self):
        _ = self.env._
        for wizard in self:
            order = wizard.order_id
            if not order:
                wizard.summary_html = False
                continue
            currency = order.currency_id
            request = order.payment_request_id
            rows = [(_("Quotation Total"), currency.format(order.amount_total))]
            if request:
                kinds = dict(request._fields["kind"]._description_selection(self.env))
                rows.append((_("Request"), kinds.get(request.kind, request.kind)))
                if request.verified_amount:
                    rows.append((_("Paid"), currency.format(request.verified_amount)))
                if request.deadline:
                    rows.append((_("Payment Deadline"), format_datetime(self.env, request.deadline)))
            body = Markup("").join(
                Markup(
                    '<div class="d-flex justify-content-between align-items-baseline py-1 gap-3">'
                    '<span class="text-muted">%s</span><span class="text-end">%s</span></div>'
                )
                % (label, escape(value))
                for label, value in rows
            )
            due = request.remaining_amount if request else order.amount_total
            footer = Markup(
                '<div class="d-flex justify-content-between align-items-baseline border-top pt-2 mt-2 fw-bold">'
                '<span>%s</span><span class="text-primary fs-5">%s</span></div>'
            ) % (_("Remaining Due"), escape(currency.format(due)))
            wizard.summary_html = Markup(
                '<div class="bg-light border rounded p-3">'
                '<div class="fw-semibold fs-5 mb-1">%s</div>'
                '<div class="text-muted small mb-3">%s</div>'
                '%s%s</div>'
            ) % (escape(order.name), escape(order.customer_id.display_name or ""), body, footer)

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
