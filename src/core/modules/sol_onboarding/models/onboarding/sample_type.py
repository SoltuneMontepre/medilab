from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE
from odoo.addons.sol_onboarding.constants.models import MODEL_ONBOARDING_ORIGIN_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_type as SampleTypeBase
else:
    SampleTypeBase = object


# Loại Mẫu
class SampleType(models.Model, SampleTypeBase):
    _name = MODEL_SAMPLE_TYPE
    _inherit = [MODEL_SAMPLE_TYPE, MODEL_ONBOARDING_ORIGIN_MIXIN]
