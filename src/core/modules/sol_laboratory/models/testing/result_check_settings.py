from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    DEFAULT_RESULT_CHECK_DEVIATIONS,
    DEFAULT_RESULT_CHECK_MARGIN,
    DEFAULT_RESULT_CHECK_MINIMUM,
    RESULT_CHECK_DEVIATIONS_PARAMETER,
    RESULT_CHECK_MARGIN_PARAMETER,
    RESULT_CHECK_MINIMUM_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # How many approved results of a way of testing on a sample type a numeric result is compared with at least.
        result_check_minimum_count = fields.Integer(
            string="Approved Results to Compare",
            config_parameter=RESULT_CHECK_MINIMUM_PARAMETER,
            default=DEFAULT_RESULT_CHECK_MINIMUM,
            help="A numeric result is compared with the approved results of its way of testing on its sample type only "
            "once there are at least this many.",
        )
        # How many standard deviations from the mean of the approved results make a result unusual.
        result_check_deviations = fields.Float(
            string="Unusual Spread (standard deviations)",
            config_parameter=RESULT_CHECK_DEVIATIONS_PARAMETER,
            default=DEFAULT_RESULT_CHECK_DEVIATIONS,
            help="A result further than this many standard deviations from the mean of the approved results is "
            "unusual.",
        )
        # How close to a regulation limit, in percent of the limit, a result is warned about.
        result_check_limit_margin_percent = fields.Float(
            string="Limit Margin (%)",
            config_parameter=RESULT_CHECK_MARGIN_PARAMETER,
            default=DEFAULT_RESULT_CHECK_MARGIN,
            help="A result within this percentage of its regulation limit is warned about before it is sent.",
        )

    @api.constrains("result_check_minimum_count", "result_check_deviations", "result_check_limit_margin_percent")
    def _check_result_check(self):
        # A spread needs two results, and a zero spread or margin would warn about nearly every value or none.
        for settings in self:
            if settings.result_check_minimum_count < 2:
                raise ValidationError(self.env._("A result is compared with at least 2 approved results."))
            if settings.result_check_deviations <= 0 or settings.result_check_limit_margin_percent < 0:
                raise ValidationError(
                    self.env._("The unusual spread must be above 0 and the limit margin cannot be negative.")
                )
