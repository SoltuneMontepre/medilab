from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB
from odoo.addons.sol_onboarding.constants.models import (
    MODEL_ONBOARDING_ORGANISATION,
    MODEL_ONBOARDING_RUN,
    MODEL_ONBOARDING_SOURCE,
)
from odoo.addons.sol_onboarding.constants.onboarding import ITEMS_OPEN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_onboarding_run as OnboardingRunGuidanceBase
else:
    OnboardingRunGuidanceBase = object


# Lượt Thu Thập: what its form tells the administrator about the organisations being listed.
class OnboardingRunGuidance(models.Model, OnboardingRunGuidanceBase):
    _inherit = MODEL_ONBOARDING_RUN

    if not TYPE_CHECKING:
        # How many organisations are listed so far, said while a refresh still has pages to read; empty otherwise.
        organisations_notice = fields.Char(string="Organisations Notice", compute="_compute_organisations_notice")

    def _compute_organisations_notice(self):
        jobs = self.env[MODEL_SCHEDULED_JOB].sudo()
        sources = self.env[MODEL_ONBOARDING_SOURCE].sudo().search([("enabled", "=", True)])
        notice = False
        if any(jobs._refresh_items(source, *ITEMS_OPEN) for source in sources):
            notice = self.env._(
                "The organisations are still being listed: %s so far. Yours can be picked as soon as it is listed.",
                self.env[MODEL_ONBOARDING_ORGANISATION].sudo().search_count([]),
            )
        for run in self:
            run.organisations_notice = notice
