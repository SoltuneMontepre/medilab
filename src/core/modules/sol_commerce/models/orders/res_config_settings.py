from odoo import fields, models

from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Days after sending before the quotation is flagged expired.
    payment_deadline_days = fields.Integer(
        config_parameter=PAYMENT_DEADLINE_PARAMETER,
        default=DEFAULT_PAYMENT_DEADLINE_DAYS,
        help="Days after a quotation is sent before it is flagged expired. "
        "Applies to quotations sent without a payment deadline.",
    )
