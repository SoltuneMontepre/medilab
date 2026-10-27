from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_QUALITY_REGISTRATION_WARNING_DAYS,
    QUALITY_REGISTRATION_WARNING_PARAMETER,
)


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days before a quality registration expires when administrators are warned.
    quality_registration_warning_days = fields.Integer(
        string="Expiry Warning (days)",
        config_parameter=QUALITY_REGISTRATION_WARNING_PARAMETER,
        default=DEFAULT_QUALITY_REGISTRATION_WARNING_DAYS,
        help="Days before a quality registration expires when administrators are warned. They are warned again on "
        "its last valid day.",
    )

    @api.constrains("quality_registration_warning_days")
    def _check_quality_registration_warning(self):
        # A negative period would never warn, not even on the last valid day.
        if any(settings.quality_registration_warning_days < 0 for settings in self):
            raise ValidationError(
                self.env._("The expiry warning cannot be negative; 0 warns only on the last valid day.")
            )
