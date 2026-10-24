from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_UPLOAD_HOURS,
    LABORATORY_UPLOAD_PARAMETER,
    LIFECYCLE_ABORT_HOURS,
)


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Hours a computer has to upload a file and finalize it before the upload expires.
    laboratory_upload_hours = fields.Integer(
        string="Unfinished Uploads (hours)",
        config_parameter=LABORATORY_UPLOAD_PARAMETER,
        default=DEFAULT_LABORATORY_UPLOAD_HOURS,
        help="Hours a computer has to upload a laboratory file and finalize it; an upload not finalized by then expires "
        "and its parts are removed.",
    )

    @api.constrains("laboratory_upload_hours")
    def _check_laboratory_upload_hours(self):
        # The bucket aborts incomplete uploads after 7 days, so an upload must expire before.
        if any(not 1 <= settings.laboratory_upload_hours < LIFECYCLE_ABORT_HOURS for settings in self):
            raise ValidationError(
                self.env._(
                    "An unfinished upload lasts at least 1 hour and less than 7 days, when the bucket aborts it."
                )
            )
