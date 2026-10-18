from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_SIGNING_CERTIFICATE_ALERT_DAYS,
    DIGITAL_SIGNING_PARAMETER,
    SIGNING_CERTIFICATE_ALERT_PARAMETER,
)


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Whether fully signed documents print as the PDF Viettel Sign signed.
    digital_signing_enabled = fields.Boolean(
        string="Digital Signing",
        config_parameter=DIGITAL_SIGNING_PARAMETER,
        help="Fully signed documents print as the PDF Viettel Sign signed with the laboratory's certificate. "
        "The Viettel Sign account comes from the server's environment.",
    )
    # Days before the laboratory's certificate expires when administrators are alerted.
    signing_certificate_alert_days = fields.Integer(
        string="Certificate Alert (days)",
        config_parameter=SIGNING_CERTIFICATE_ALERT_PARAMETER,
        default=DEFAULT_SIGNING_CERTIFICATE_ALERT_DAYS,
        help="Days before the laboratory's certificate expires when administrators are alerted.",
    )
