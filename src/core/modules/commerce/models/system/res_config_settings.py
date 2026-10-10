from odoo import fields, models

from odoo.addons.laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS

INVOICE_DUE_DAYS = "invoice_due_days"


# Cấu Hình Hệ Thống
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days a customer has to pay an invoice after it is posted.
    invoice_due_days = fields.Integer(
        config_parameter="medilab.commerce.invoice_due_days",
        default=7,
        help="Days a customer has to pay an invoice after it is posted.",
    )
