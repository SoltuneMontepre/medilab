from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE


# Hóa Đơn: paying the advance invoice accepts the quotation.
class AccountMove(models.Model):
    _inherit = MODEL_ACCOUNT_MOVE

    def _invoice_paid_hook(self):
        result = super()._invoice_paid_hook()
        orders = self.line_ids.sale_line_ids.filtered("is_downpayment").order_id
        for order in orders:
            order._latest_quotation()._accept()
        return result
