from odoo import fields, models

from odoo.addons.sol_laboratory.constants.settings import DEFAULT_SAFETY_MARGIN_DAYS, SAFETY_MARGIN_PARAMETER


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Days a sample test is due before the date promised to the customer, kept for handling incidents.
    safety_margin_days = fields.Integer(
        config_parameter=SAFETY_MARGIN_PARAMETER,
        default=DEFAULT_SAFETY_MARGIN_DAYS,
        help="Days a sample test is due before the date promised to the customer, kept for handling incidents. "
        "Applies to sample tests whose due date is worked out from now on.",
    )
