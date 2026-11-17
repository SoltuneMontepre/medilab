from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS
from odoo.addons.sol_laboratory.constants.settings import (
    MOBILE_MINIMUM_VERSION_PARAMETER,
    MOBILE_STOPPED_VERSIONS_PARAMETER,
)
from odoo.addons.sol_laboratory.services.mobile_releases import parse_versions
from odoo.addons.sol_laboratory.services.sync_releases import version_key

if TYPE_CHECKING:
    from medilab_model_types import Model_res_config_settings as ResConfigSettingsBase
else:
    ResConfigSettingsBase = object


# Cài Đặt
class ResConfigSettings(models.TransientModel, ResConfigSettingsBase):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    if not TYPE_CHECKING:
        # The oldest Medilab Mobile version MediLab still serves; empty serves every version.
        mobile_minimum_version = fields.Char(
            string="Oldest Version Served",
            config_parameter=MOBILE_MINIMUM_VERSION_PARAMETER,
            help="A phone running an older version of Medilab Mobile must update before it is used, and shows only "
            "the updating screen while no release reaches this version. Empty serves every version.",
        )
        # The Medilab Mobile versions MediLab no longer serves, separated by commas.
        mobile_stopped_versions = fields.Char(
            string="Stopped Releases",
            config_parameter=MOBILE_STOPPED_VERSIONS_PARAMETER,
            help="Versions of Medilab Mobile no phone downloads any more, separated by commas, such as 1.2.0, 1.2.1. "
            "Phones that run a stopped version take the next release the release pipeline publishes.",
        )

    @api.constrains("mobile_minimum_version", "mobile_stopped_versions")
    def _check_mobile_versions(self):
        for settings in self:
            versions = parse_versions(settings.mobile_stopped_versions) + parse_versions(
                settings.mobile_minimum_version
            )
            for version in versions:
                try:
                    version_key(version)
                except ValueError:
                    raise ValidationError(
                        self.env._("%(version)s is not a version such as 1.2.3.", version=version)
                    ) from None
