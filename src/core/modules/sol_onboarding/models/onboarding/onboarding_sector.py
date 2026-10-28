from odoo import fields, models

from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_SECTOR


# Ngành
class OnboardingSector(models.Model):
    _name = MODEL_ONBOARDING_SECTOR
    _description = "Onboarding Sector"
    _order = "id"

    _code_unique = models.Constraint("UNIQUE(code)", "A sector code is used once.")

    # Short technical name the sources and adapters refer to the sector by.
    code = fields.Char(string="Code", required=True)
    # Name shown to people.
    name = fields.Char(string="Name", required=True, translate=True)
