from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOT
from odoo.addons.sol_inventory.constants.settings import DEFAULT_EXPIRY_WARNING_DAYS, EXPIRY_WARNING_PARAMETER
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days before a lot or container stops being usable when it is listed and notified as expiring soon.
    expiry_warning_days = fields.Integer(
        config_parameter=EXPIRY_WARNING_PARAMETER,
        default=DEFAULT_EXPIRY_WARNING_DAYS,
        help="Lots and containers usable for fewer days than this are listed and notified as expiring soon.",
    )

    @api.constrains("expiry_warning_days")
    def _check_expiry_warning(self):
        if any(settings.expiry_warning_days < 0 for settings in self):
            raise ValidationError(self.env._("The days before expiry cannot be negative."))

    def set_values(self):
        result = super().set_values()
        self.env[MODEL_STOCK_LOT]._apply_expiry_warning(self._get_parameter("expiry_warning_days"))
        return result
