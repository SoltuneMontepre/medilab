from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_METHOD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_method as TestingMethodBase
else:
    TestingMethodBase = object


# Phương Pháp Thử
class TestingMethod(models.Model, TestingMethodBase):
    _name = MODEL_TESTING_METHOD
    _inherit = [MODEL_TESTING_METHOD, MODEL_ONBOARDING_ORIGIN_MIXIN]
