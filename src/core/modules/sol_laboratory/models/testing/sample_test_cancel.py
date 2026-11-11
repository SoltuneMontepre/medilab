from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_SAMPLE_TEST_CANCEL

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test_cancel as SampleTestCancelBase
else:
    SampleTestCancelBase = object


# Hủy Chỉ Tiêu Của Mẫu
class SampleTestCancel(models.TransientModel, SampleTestCancelBase):
    _name = MODEL_SAMPLE_TEST_CANCEL
    _description = "Cancel a Sample Test"

    if not TYPE_CHECKING:
        # The sample test cancelled.
        sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, required=True, ondelete="cascade")
        # Why the test is cancelled, such as the parameter cannot be tested on the sample.
        reason = fields.Text(required=True)

    def action_cancel(self):
        self.ensure_one()
        self.sample_test_id.action_cancel(self.reason)
        return {"type": "ir.actions.act_window_close"}
