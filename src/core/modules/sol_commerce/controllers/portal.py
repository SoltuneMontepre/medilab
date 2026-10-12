from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request

from odoo.addons.account.controllers.portal import PortalAccount


class InvoicePortal(PortalAccount):
    def portal_my_invoice_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        # A customer opens only their own posted invoices. A token still has to name that invoice.
        try:
            invoice = self._document_check_access("account.move", invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if invoice.state != "posted" or invoice.move_type not in ("out_invoice", "out_refund"):
            return request.redirect("/my")
        return super().portal_my_invoice_detail(
            invoice_id, access_token=access_token, report_type=report_type, download=download, **kw
        )

    @http.route("/my/invoices/<int:invoice_id>/pay", type="http", auth="user", methods=["POST"], website=True)
    def portal_pay_invoice(self, invoice_id, method="bank_transfer", **kwargs):
        # The amount is computed on the server. kwargs may contain a forged amount and it is ignored.
        try:
            invoice = self._document_check_access("account.move", invoice_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if method == "payos":
            try:
                transaction = request.env["payment.transaction"].portal_start_payos(invoice)
            except (AccessError, UserError):
                return request.redirect(f"/my/invoices/{invoice_id}")
            if transaction.payos_checkout_url:
                return request.redirect(transaction.payos_checkout_url, local=False)
            return request.redirect(f"/my/invoices/{invoice_id}")
        try:
            request.env["account.payment"].portal_pay_invoice(invoice)
        except (AccessError, UserError):
            return request.redirect("/my")
        return request.redirect(f"/my/invoices/{invoice_id}")

    @http.route("/my/invoices/<int:invoice_id>/receipt/<int:payment_id>", type="http", auth="user", website=True)
    def portal_payment_receipt(self, invoice_id, payment_id, **kwargs):
        try:
            invoice = self._document_check_access("account.move", invoice_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        payment = request.env["account.payment"].sudo().browse(payment_id).exists()
        same_invoice = payment and invoice in payment.invoice_ids
        same_customer = payment and payment.partner_id.commercial_partner_id == invoice.partner_id.commercial_partner_id
        if not same_invoice or not same_customer:
            return request.redirect("/my")
        html = request.env["ir.actions.report"].sudo()._render_qweb_html(
            "account.action_report_payment_receipt", payment.ids
        )[0]
        return request.make_response(html, headers=[("Content-Type", "text/html; charset=utf-8")])
