from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_parameter as TestParameterBase
else:
    TestParameterBase = object


# Chỉ Tiêu
class TestParameter(models.Model, TestParameterBase):
    _name = MODEL_TEST_PARAMETER
    _inherit = [MODEL_TEST_PARAMETER, MODEL_ONBOARDING_ORIGIN_MIXIN]
