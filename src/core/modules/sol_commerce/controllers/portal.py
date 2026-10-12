from odoo import http
from odoo.exceptions import AccessError, MissingError
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

    @http.route("/my/invoices/<int:invoice_id>/pay", type="http", auth="user", methods=["POST"], csrf=False)
    def portal_pay_invoice(self, invoice_id, **kwargs):
        # amount in the request is ignored. The customer pays what the invoice still owes.
        try:
            invoice = self._document_check_access("account.move", invoice_id)
        except (AccessError, MissingError):
            return request.redirect("/my")
        request.env["account.payment"].portal_pay_invoice(invoice)
        return request.redirect(f"/my/invoices/{invoice_id}")
