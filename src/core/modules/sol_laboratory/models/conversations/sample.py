from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_CHATTER_MIXIN, MODEL_SAMPLE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample as SampleChatterBase
else:
    SampleChatterBase = object


# Mẫu: its chatter.
class SampleChatter(models.Model, SampleChatterBase):
    _name = MODEL_SAMPLE
    _inherit = [MODEL_SAMPLE, MODEL_CHATTER_MIXIN]
