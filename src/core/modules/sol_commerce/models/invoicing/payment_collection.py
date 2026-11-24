import base64
from typing import TYPE_CHECKING

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.tools import format_datetime

from odoo.addons.sol_commerce.constants.models import (
    MODEL_PAYMENT_COLLECTION,
    MODEL_PAYMENT_TRANSACTION,
    MODEL_SALE_ORDER,
)

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
        # Whether PayOS is enabled for generating a live checkout QR on the active payment request.
        payos_available = fields.Boolean(compute="_compute_qr_info")
        # Active PayOS checkout URL for the order's current payment request, when already created.
        payos_checkout_url = fields.Char(compute="_compute_qr_info")
        # VietQR or PayOS QR block shown when bank transfer is selected so Sales can show or print it for the client.
        qr_html = fields.Html(compute="_compute_qr_info", sanitize=False)

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
            rows = [(_("Quotation total"), currency.format(order.amount_total))]
            if request:
                kinds = dict(request._fields["kind"]._description_selection(self.env))
                rows.append((_("Payment request"), kinds.get(request.kind or "", request.kind)))
                if request.verified_amount:
                    rows.append((_("Paid amount"), currency.format(request.verified_amount)))
                if request.deadline:
                    rows.append((_("Due by"), format_datetime(self.env, request.deadline)))
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
            ) % (_("Remaining due"), escape(currency.format(due)))
            quotation = request.quotation_id if request and request.quotation_id else order._latest_quotation()
            target = quotation or order
            label = quotation.code if quotation else order.name
            title = Markup(
                '<a href="#" class="fw-semibold fs-5 text-decoration-none" data-res-model="%s" data-res-id="%s">%s</a>'
            ) % (escape(target._name), target.id, escape(label))
            wizard.summary_html = Markup(
                '<div class="bg-light border rounded p-3 w-100">'
                '<div class="mb-1">%s</div>'
                '<div class="text-muted small mb-3">%s</div>'
                "%s%s</div>"
            ) % (title, escape(order.customer_id.display_name or ""), body, footer)

    @api.depends("order_id", "method", "amount", "reference")
    def _compute_qr_info(self):
        _ = self.env._
        for wizard in self:
            order = wizard.order_id
            payos_available = bool(order and order._payment_request_payos_available())
            request = order.payment_request_id if order else False
            tx = (
                request.sudo()
                .transaction_ids.filtered(
                    lambda item: (
                        item.provider_code == "payos"
                        and not item.payos_link_closed
                        and bool(item.payos_checkout_url)
                        and item.state in ("draft", "pending")
                    )
                )
                .sorted("id", reverse=True)[:1]
                if request
                else self.env[MODEL_PAYMENT_TRANSACTION]
            )
            checkout_url = tx.payos_checkout_url or False
            wizard.payos_available = payos_available
            wizard.payos_checkout_url = checkout_url
            if not order or wizard.method != "bank_transfer":
                wizard.qr_html = False
                continue
            amount = wizard.amount or (request.remaining_amount if request else order.amount_total)
            memo = wizard.reference or (request.quotation_id.code if request and request.quotation_id else order.name)
            if checkout_url:
                png = self.env["ir.actions.report"].barcode("QR", checkout_url, width=200, height=200)
                img_src = f"data:image/png;base64,{base64.b64encode(png).decode()}"
                wizard.qr_html = Markup(
                    '<div class="border rounded p-3 bg-light text-center">'
                    '<div class="fw-semibold mb-2">%s</div>'
                    '<img src="%s" alt="PayOS QR" class="img-fluid mb-2" style="max-width: 180px;" />'
                    '<div class="small text-muted mb-2">%s: <span class="fw-semibold text-dark">%s</span></div>'
                    '<div class="d-flex justify-content-center gap-2">'
                    '<a href="%s" target="_blank" rel="noopener" class="btn btn-sm btn-outline-primary">%s</a>'
                    '<button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.print()">%s</button>'
                    "</div></div>"
                ) % (
                    _("Scan to pay with PayOS"),
                    img_src,
                    escape(self.fields_get(["amount"])["amount"]["string"]),
                    escape(order.currency_id.format(amount)),
                    escape(checkout_url),
                    _("Open PayOS link"),
                    _("Print QR"),
                )
                continue
            bank = order.company_id.sudo().partner_id.bank_ids[:1]
            if bank:
                qr_b64 = bank.build_qr_code_base64(
                    amount, memo, False, order.currency_id, order.partner_id, silent_errors=True
                )
                qr_img = (
                    Markup(
                        '<img src="data:image/png;base64,%s" alt="Bank QR" class="img-fluid mb-2" style="max-width: 180px;" />'
                    )
                    % qr_b64
                    if qr_b64
                    else Markup("")
                )
                holder = bank.holder_name or order.company_id.name
                wizard.qr_html = Markup(
                    '<div class="border rounded p-3 bg-light text-center">'
                    '<div class="fw-semibold mb-2">%s</div>'
                    "%s"
                    '<div class="small text-start mt-1">'
                    '<div><span class="text-muted">%s:</span> %s</div>'
                    '<div><span class="text-muted">%s:</span> <span class="fw-semibold">%s</span></div>'
                    '<div><span class="text-muted">%s:</span> %s</div>'
                    '<div><span class="text-muted">%s:</span> <span class="fw-semibold">%s</span></div>'
                    "</div>"
                    '<div class="mt-2">'
                    '<button type="button" class="btn btn-sm btn-outline-secondary" onclick="window.print()">%s</button>'
                    "</div></div>"
                ) % (
                    _("Bank transfer QR"),
                    qr_img,
                    _("Bank"),
                    escape(bank.bank_name or ""),
                    _("Account number"),
                    escape(bank.account_number or ""),
                    _("Account holder"),
                    escape(holder or ""),
                    _("Transfer content"),
                    escape(memo or ""),
                    _("Print QR"),
                )
                continue
            wizard.qr_html = Markup('<div class="alert alert-secondary mb-0 small">%s</div>') % _(
                "PayOS or a company bank account is not configured to generate a payment QR yet."
            )

    def action_generate_payos_qr(self):
        self.ensure_one()
        request = self.order_id.payment_request_id
        if request:
            self.env[MODEL_PAYMENT_TRANSACTION]._portal_start_request_payos(request, self.amount)
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_PAYMENT_COLLECTION,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        order = self.env[MODEL_SALE_ORDER].browse(values.get("order_id") or self.env.context.get("default_order_id"))
        if not order:
            return values
        if "amount" in fields_list and not values.get("amount"):
            request = order.payment_request_id
            values["amount"] = (
                max(order.currency_id.round(request.remaining_amount - request.pending_amount), 0)
                if request
                else order.amount_total
            )
        if "method" in fields_list and not values.get("method") and order.payment_method in ("cash", "bank_transfer"):
            values["method"] = order.payment_method
        return values

    def action_record(self):
        self.ensure_one()
        self.order_id.action_record_collection(self.amount, self.method, self.received_at, self.reference)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Payment recorded; pending accounting confirmation."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
