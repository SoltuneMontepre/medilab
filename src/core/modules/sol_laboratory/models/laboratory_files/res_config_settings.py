from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_LABORATORY_EDITING_IDLE_HOURS,
    DEFAULT_LABORATORY_FOLDER_RETENTION_DAYS,
    LABORATORY_EDITING_IDLE_PARAMETER,
    LABORATORY_FOLDER_RETENTION_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
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

    if not TYPE_CHECKING:
        # Hours an online editing session can go without activity before it expires and nobody joins it any more.
        laboratory_editing_idle_hours = fields.Integer(
            string="Idle Editing Sessions (hours)",
            config_parameter=LABORATORY_EDITING_IDLE_PARAMETER,
            default=DEFAULT_LABORATORY_EDITING_IDLE_HOURS,
            help="Hours an online editing session can go without activity before it expires; people still editing lose "
            "nothing, and the next person opening the file starts a new session.",
        )

    @api.constrains("laboratory_editing_idle_hours")
    def _check_laboratory_editing_idle_hours(self):
        # A period of 0 would expire a session as soon as it opens.
        if any(settings.laboratory_editing_idle_hours < 1 for settings in self):
            raise ValidationError(self.env._("The idle period of editing sessions must be at least 1 hour."))
