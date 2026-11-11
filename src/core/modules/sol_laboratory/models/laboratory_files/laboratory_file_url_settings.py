from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_FILE_URL_MINUTES,
    LABORATORY_FILE_URL_PARAMETER,
    LONGEST_LABORATORY_FILE_URL_MINUTES,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # Minutes a presigned address of a laboratory file version's content lasts.
        laboratory_file_url_minutes = fields.Integer(
            string="File Addresses (minutes)",
            config_parameter=LABORATORY_FILE_URL_PARAMETER,
            default=DEFAULT_LABORATORY_FILE_URL_MINUTES,
            help="Minutes an address that downloads a version of a laboratory file, or opens it in the online editor, "
            "keeps working once it is given.",
        )

    @api.constrains("laboratory_file_url_minutes")
    def _check_laboratory_file_url_minutes(self):
        if any(
            not 1 <= settings.laboratory_file_url_minutes <= LONGEST_LABORATORY_FILE_URL_MINUTES for settings in self
        ):
            raise ValidationError(
                self.env._(
                    "An address of a laboratory file lasts from 1 minute to 7 days, the longest the bucket takes."
                )
            )
