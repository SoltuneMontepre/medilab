from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_FOLDER_RETENTION_DAYS,
    LABORATORY_FOLDER_RETENTION_PARAMETER,
)


# Cài Đặt
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days an archived laboratory folder keeps its files and versions after it is archived.
    laboratory_folder_retention_days = fields.Integer(
        string="Archived Folders (days)",
        config_parameter=LABORATORY_FOLDER_RETENTION_PARAMETER,
        default=DEFAULT_LABORATORY_FOLDER_RETENTION_DAYS,
        help="Days an archived laboratory folder keeps its files and versions; archiving a folder sets its retention "
        "date this many days later.",
    )

    @api.constrains("laboratory_folder_retention_days")
    def _check_laboratory_folder_retention(self):
        # A period of 0 would end an archived folder's retention on the day it is archived.
        if any(settings.laboratory_folder_retention_days < 1 for settings in self):
            raise ValidationError(self.env._("The retention period of archived folders must be at least 1 day."))
