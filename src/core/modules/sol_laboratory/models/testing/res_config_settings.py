from odoo import api, fields, models
from odoo.tools import clean_context

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_SAFETY_MARGIN_DAYS, SAFETY_MARGIN_PARAMETER


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    @api.model
    def _get_parameter(self, field_name):
        # sudo: only administrators may read system parameters, while features read them for everyone.
        field = self._fields[field_name]
        stored = self.env["ir.config_parameter"].sudo().get_str(field.config_parameter)
        if stored in (False, None, ""):
            default = field.default
            return default(self) if callable(default) else default
        settings = self.with_context(clean_context(dict(self.env.context))).sudo()
        return settings.default_get([field_name])[field_name]

    # Days a sample test is due before the date promised to the customer, kept for handling incidents.
    safety_margin_days = fields.Integer(
        config_parameter=SAFETY_MARGIN_PARAMETER,
        default=DEFAULT_SAFETY_MARGIN_DAYS,
        help="Days a sample test is due before the date promised to the customer, kept for handling incidents. "
        "Applies to sample tests whose due date is worked out from now on.",
    )
