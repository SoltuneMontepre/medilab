from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_QUOTATION


# Hóa Đơn: paying the advance invoice accepts the quotation.
class AccountMove(models.Model):
    _inherit = MODEL_ACCOUNT_MOVE

    def _invoice_paid_hook(self):
        result = super()._invoice_paid_hook()
        # Only the quotation the invoice was sent with, and only while it is still sent.
        self.env[MODEL_QUOTATION].sudo().search([("advance_invoice_id", "in", self.ids)])._accept()
        return result
