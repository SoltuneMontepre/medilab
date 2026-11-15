from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    CALIBRATION_WARNING_PARAMETER,
    DEFAULT_MACHINE_WARNING_DAYS,
    DEFAULT_QUALITY_REGISTRATION_WARNING_DAYS,
    MAINTENANCE_WARNING_PARAMETER,
    QUALITY_REGISTRATION_WARNING_PARAMETER,
    REPAIR_WARNING_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # Days before a quality registration expires when administrators are warned.
        quality_registration_warning_days = fields.Integer(
            string="Expiry Warning (days)",
            config_parameter=QUALITY_REGISTRATION_WARNING_PARAMETER,
            default=DEFAULT_QUALITY_REGISTRATION_WARNING_DAYS,
            help="Days before a quality registration expires when administrators are warned. They are warned again on "
            "its last valid day.",
        )
        # Days before a machine's calibration ends within which its bookings warn.
        calibration_warning_days = fields.Integer(
            string="Calibration Warning (days)",
            config_parameter=CALIBRATION_WARNING_PARAMETER,
            default=DEFAULT_MACHINE_WARNING_DAYS,
            help="A booking that ends within this many days before its machine's calibration ends warns its tester.",
        )
        # Days before a machine's maintenance is due within which its bookings warn.
        maintenance_warning_days = fields.Integer(
            string="Maintenance Warning (days)",
            config_parameter=MAINTENANCE_WARNING_PARAMETER,
            default=DEFAULT_MACHINE_WARNING_DAYS,
            help="A booking that ends within this many days before its machine's maintenance is due warns its tester.",
        )
        # Days after a machine's repair within which its bookings warn.
        repair_warning_days = fields.Integer(
            string="Recent Repair Warning (days)",
            config_parameter=REPAIR_WARNING_PARAMETER,
            default=DEFAULT_MACHINE_WARNING_DAYS,
            help="A booking that starts within this many days after its machine's repair warns its tester.",
        )

    @api.constrains("quality_registration_warning_days")
    def _check_quality_registration_warning(self):
        # A negative period would never warn, not even on the last valid day.
        if any(settings.quality_registration_warning_days < 0 for settings in self):
            raise ValidationError(
                self.env._("The expiry warning cannot be negative; 0 warns only on the last valid day.")
            )

    @api.constrains("calibration_warning_days", "maintenance_warning_days", "repair_warning_days")
    def _check_machine_warnings(self):
        for settings in self:
            days = (settings.calibration_warning_days, settings.maintenance_warning_days, settings.repair_warning_days)
            if min(days) < 0:
                raise ValidationError(self.env._("A machine warning cannot be negative; 0 turns it off."))
