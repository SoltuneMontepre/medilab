from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN


# Loại Mẫu
class SampleType(models.Model):
    _name = MODEL_SAMPLE_TYPE
    _inherit = [MODEL_SAMPLE_TYPE, MODEL_ONBOARDING_ORIGIN_MIXIN]
