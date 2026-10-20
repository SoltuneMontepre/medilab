from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE, MODEL_INVOICE_ADJUSTMENT
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN


# Điều chỉnh hóa đơn
class InvoiceAdjustment(models.TransientModel):
    _name = MODEL_INVOICE_ADJUSTMENT
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Invoice Adjustment"
    # The accountant enters the difference; the wizard does not keep it.
    _permission_actions = ("read", "create", "edit", "delete")

    # The posted invoice being corrected.
    move_id = fields.Many2one(MODEL_ACCOUNT_MOVE, required=True)
    # Signed difference added to what is owed. Negative lowers the invoice.
    difference = fields.Monetary(required=True)
    # Currency of the invoice.
    currency_id = fields.Many2one(related="move_id.currency_id")

    def action_adjust(self):
        self.ensure_one()
        adjustment = self.move_id.action_adjust(self.difference)
        return adjustment._get_records_action()
