from odoo import api, models
from odoo.tools import clean_context

from odoo.addons.laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS


# Cấu Hình Hệ Thống
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    @api.model
    def _get_parameter(self, field_name):
        """The value of a settings field stored as a system parameter, or the field's default when it is missing."""
        # default_get reads the parameter and converts it as the settings screen does; sudo because only
        # administrators may read parameters, while features read them for everyone.
        settings = self.with_context(clean_context(dict(self.env.context))).sudo()
        return settings.default_get([field_name])[field_name]
