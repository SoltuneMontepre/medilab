from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_TESTING_FIELD
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_field as TestingFieldBase
else:
    TestingFieldBase = object


# Lĩnh Vực Thử Nghiệm
class TestingField(models.Model, TestingFieldBase):
    _name = MODEL_TESTING_FIELD
    _inherit = [MODEL_TESTING_FIELD, MODEL_ONBOARDING_ORIGIN_MIXIN]
