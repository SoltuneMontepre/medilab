from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACTOR
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORGANISATION

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontractor as SubcontractorBase
else:
    SubcontractorBase = object


# Thầu Phụ: its accreditation number checked against the organisations the sources list.
class Subcontractor(models.Model, SubcontractorBase):
    _inherit = MODEL_SUBCONTRACTOR

    if not TYPE_CHECKING:
        # What the listed organisations say about the accreditation number; empty without a number or a list.
        accreditation_listing = fields.Char(string="Accreditation Listing", compute="_compute_accreditation_listing")
        # True when a listed organisation has the accreditation number.
        accreditation_listed = fields.Boolean(string="Accreditation Listed", compute="_compute_accreditation_listing")

    @api.depends("accreditation_number")
    def _compute_accreditation_listing(self):
        organisations = self.env[MODEL_ONBOARDING_ORGANISATION].sudo()
        any_listed = bool(organisations.search_count([], limit=1))
        for subcontractor in self:
            number = " ".join((subcontractor.accreditation_number or "").split())
            listed = (
                organisations.search([("accreditation_code", "=ilike", number)], limit=1) if number else organisations
            )
            subcontractor.accreditation_listed = bool(listed)
            if listed:
                subcontractor.accreditation_listing = self.env._("Listed as %s.", listed.name)
            elif number and any_listed:
                subcontractor.accreditation_listing = self.env._(
                    "No listed organisation has this accreditation number."
                )
            else:
                subcontractor.accreditation_listing = False
