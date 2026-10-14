from odoo import http

from odoo.addons.account.controllers.download_docs import AccountDocumentDownloadController


class MedilabDownloadDocs(AccountDocumentDownloadController):
    @http.route()
    def download_invoice_attachments(self, attachments):
        response = super().download_invoice_attachments(attachments)
        # Odoo reads the files itself here, not through its content routes.
        for attachment in attachments._audit_scope():
            attachment._audit("download", attachment.name)
        return response
