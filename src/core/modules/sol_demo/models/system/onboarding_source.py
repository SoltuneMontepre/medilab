from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_onboarding_source as OnboardingSourceBase
else:
    OnboardingSourceBase = object


# Nguồn Tin Cậy
class OnboardingSource(models.Model, OnboardingSourceBase):
    _inherit = MODEL_ONBOARDING_SOURCE

    @api.model
    def _seed_onboarding_demo(self):
        """Turn every source off, so a demo never reaches a source. Safe to run again."""
        self.sudo().with_context(active_test=False).search([]).enabled = False
