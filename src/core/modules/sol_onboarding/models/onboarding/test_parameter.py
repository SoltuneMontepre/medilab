from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN


# Chỉ Tiêu
class TestParameter(models.Model):
    _name = MODEL_TEST_PARAMETER
    _inherit = [MODEL_TEST_PARAMETER, MODEL_ONBOARDING_ORIGIN_MIXIN]
