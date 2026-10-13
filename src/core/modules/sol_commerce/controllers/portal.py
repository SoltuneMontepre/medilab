import logging
from urllib.parse import urlsplit

from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from odoo.addons.account.controllers.portal import PortalAccount
from odoo.addons.sol_commerce.constants.models import (
    MODEL_ACCOUNT_MOVE,
    MODEL_ACCOUNT_PAYMENT,
    MODEL_PAYMENT_TRANSACTION,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM
from odoo.addons.sol_laboratory.services.request_env import request_env

_logger = logging.getLogger(__name__)

# website=True makes a route a frontend page. The http_routing addon reads it, and odoo.http does not declare it
# among the route options, so pyright rejects it as a keyword.
FRONTEND_PAGE = {"website": True}


class InvoicePortal(PortalAccount):
    @http.route(["/my/invoices/<int:invoice_id>"], type="http", auth="public", **FRONTEND_PAGE)
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        # A customer opens only their own posted invoices. A token still has to name that invoice.
        try:
            invoice = self._document_check_access(MODEL_ACCOUNT_MOVE, invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if invoice.state != "posted" or invoice.move_type not in ("out_invoice", "out_refund"):
            return request.redirect("/my")
        return super().portal_my_invoice_detail(
            invoice_id, access_token=access_token, report_type=report_type, download=download, **kw
        )

    @http.route("/my/invoices/<int:invoice_id>/pay", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def portal_pay_invoice(self, invoice_id, method="bank_transfer", **kwargs):
        # The posted amount is checked on the server. A forged value cannot change a payment already stored.
        try:
            invoice = self._document_check_access(MODEL_ACCOUNT_MOVE, invoice_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if method == "payos":
            return self._portal_payos(invoice, kwargs.get("amount"))
        try:
            request_env()[MODEL_ACCOUNT_PAYMENT].portal_pay_invoice(invoice, kwargs.get("amount"))
        except (AccessError, UserError):
            return request.redirect("/my")
        return request.redirect(f"/my/invoices/{invoice_id}")

    def _portal_payos(self, invoice, amount=None):
        """Start or reuse the PayOS link. The network call happens after the invoice lock is released."""
        try:
            transaction = request_env()[MODEL_PAYMENT_TRANSACTION].portal_start_payos(invoice, amount)
        except (AccessError, UserError) as error:
            return self._payos_page(invoice, failed=True, message=str(error))
        if self._payos_url_is_safe(transaction.payos_checkout_url):
            return request.redirect(transaction.payos_checkout_url, local=False)
        if transaction.payos_checkout_url:
            return self._payos_page(invoice, failed=True, message=self._invalid_link_message())
        transaction_id = transaction.id
        invoice_id = invoice.id
        # The invoice row lock ends with this commit. PayOS is called only after that, on the claimed job item.
        request_env().cr.commit()
        transaction = request_env()[MODEL_PAYMENT_TRANSACTION].sudo().browse(transaction_id)
        invoice = request_env()[MODEL_ACCOUNT_MOVE].browse(invoice_id)
        outcome, message = self._prepare_payos_link(transaction)
        transaction.invalidate_recordset(["payos_checkout_url"])
        if outcome != "failed" and self._payos_url_is_safe(transaction.payos_checkout_url):
            return request.redirect(transaction.payos_checkout_url, local=False)
        if outcome == "failed" or transaction.payos_checkout_url:
            return self._payos_page(invoice, failed=True, message=message)
        return self._payos_page(invoice, failed=False, message="")

    def _prepare_payos_link(self, transaction):
        """Claim the queued PayOS item and run it once. A worker that already claimed it is not run again."""
        item = (
            request_env()[MODEL_JOB_ITEM]
            .sudo()
            .search(
                [
                    ("item_key", "=", transaction.reference),
                    ("job_id.key", "=", "payos.calls"),
                ],
                limit=1,
            )
        )
        if not item or item.status in ("running", "done", "cancelled"):
            return "pending", ""
        if item.status == "failed":
            return "failed", item.last_error or self._invalid_link_message()
        job = item.job_id
        if not job._claim_pending_item(item):
            return "pending", ""
        job._run_claimed_item(item)
        item.invalidate_recordset(["status", "last_error"])
        if item.status == "failed":
            return "failed", item.last_error or self._invalid_link_message()
        _logger.info("PayOS link for order %s is %s", transaction.reference, item.status)
        return "pending", ""

    def _invalid_link_message(self):
        return request_env()._("The payment link is not valid.")

    def _payos_url_is_safe(self, url):
        if not isinstance(url, str) or not url:
            return False
        parts = urlsplit(url)
        return parts.scheme == "https" and bool(parts.hostname)

    def _payos_page(self, invoice, failed, message):
        return request.render(
            "sol_commerce.portal_payos_pending",
            {"invoice": invoice, "failed": failed, "message": message},
        )

    @http.route("/my/invoices/<int:invoice_id>/receipt/<int:payment_id>", type="http", auth="user", **FRONTEND_PAGE)
    def portal_payment_receipt(self, invoice_id, payment_id, **kwargs):
        try:
            invoice = self._document_check_access(MODEL_ACCOUNT_MOVE, invoice_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        payment = request_env()[MODEL_ACCOUNT_PAYMENT].sudo().browse(payment_id).exists()
        same_invoice = payment and invoice in payment.invoice_ids
        same_customer = payment and payment.partner_id.commercial_partner_id == invoice.partner_id.commercial_partner_id
        if not same_invoice or not same_customer:
            return request.redirect("/my")
        html = (
            request_env()["ir.actions.report"]
            .sudo()
            ._render_qweb_html("account.action_report_payment_receipt", payment.ids)[0]
        )
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
