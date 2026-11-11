from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SECTOR

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_onboarding_sector as OnboardingSectorBase
else:
    OnboardingSectorBase = object


# Ngành
class OnboardingSector(models.Model, OnboardingSectorBase):
    _name = MODEL_ONBOARDING_SECTOR
    _description = "Onboarding Sector"
    _order = "id"

    _code_unique = models.Constraint("UNIQUE(code)", "A sector code is used once.")

    if not TYPE_CHECKING:
        # Short technical name the sources and adapters refer to the sector by.
        code = fields.Char(string="Code", required=True)
        # Name shown to people.
        name = fields.Char(string="Name", required=True, translate=True)
