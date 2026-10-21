from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_METHOD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN


# Phương Pháp Thử
class TestingMethod(models.Model):
    _name = MODEL_TESTING_METHOD
    _inherit = [MODEL_TESTING_METHOD, MODEL_ONBOARDING_ORIGIN_MIXIN]
