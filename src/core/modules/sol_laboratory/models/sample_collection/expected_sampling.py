from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_EXPECTED_SAMPLING,
    MODEL_PERMISSION_MIXIN,
    MODEL_SAMPLE,
    MODEL_SAMPLING_SNAPSHOT_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_expected_sampling as ExpectedSamplingBase
else:
    ExpectedSamplingBase = object


# Nhu Cầu Lấy Mẫu Dự Kiến
class ExpectedSampling(models.Model, ExpectedSamplingBase):
    _name = MODEL_EXPECTED_SAMPLING
    _inherit = [MODEL_SAMPLING_SNAPSHOT_MIXIN, MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Expected Sampling"
    _order = "sample_id, group_number, id"
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # The sample of the test request the sampling needs are expected for.
        sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="cascade", index=True)
