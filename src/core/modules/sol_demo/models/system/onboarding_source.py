from odoo import api, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SOURCE


# Nguồn Tin Cậy
class OnboardingSource(models.Model):
    _inherit = MODEL_ONBOARDING_SOURCE

    @api.model
    def _seed_onboarding_demo(self):
        """Turn every source off, so a demo never reaches a source. Safe to run again."""
        self.sudo().with_context(active_test=False).search([]).enabled = False
