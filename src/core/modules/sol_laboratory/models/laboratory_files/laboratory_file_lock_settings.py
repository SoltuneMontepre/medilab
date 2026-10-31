from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_FILE_LOCK_MINUTES,
    LABORATORY_FILE_LOCK_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # Minutes a lock on a laboratory file lasts unless its holder renews it.
        laboratory_file_lock_minutes = fields.Integer(
            string="File Locks (minutes)",
            config_parameter=LABORATORY_FILE_LOCK_PARAMETER,
            default=DEFAULT_LABORATORY_FILE_LOCK_MINUTES,
            help="Minutes a lock on a laboratory file lasts unless the person holding it renews it; others cannot save the "
            "file meanwhile.",
        )

    @api.constrains("laboratory_file_lock_minutes")
    def _check_laboratory_file_lock_minutes(self):
        # A duration of 0 would expire every lock as it is taken.
        if any(settings.laboratory_file_lock_minutes < 1 for settings in self):
            raise ValidationError(self.env._("A lock on a laboratory file must last at least 1 minute."))
