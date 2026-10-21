from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_FIELD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN


# Lĩnh Vực Thử Nghiệm
class TestingField(models.Model):
    _name = MODEL_TESTING_FIELD
    _inherit = [MODEL_TESTING_FIELD, MODEL_ONBOARDING_ORIGIN_MIXIN]
