from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_SAMPLE_TEST_URGENT_MARK

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test_urgent_mark as SampleTestUrgentMarkBase
else:
    SampleTestUrgentMarkBase = object


# Đánh Dấu Khẩn Chỉ Tiêu Của Mẫu
class SampleTestUrgentMark(models.TransientModel, SampleTestUrgentMarkBase):
    _name = MODEL_SAMPLE_TEST_URGENT_MARK
    _description = "Mark a Sample Test Urgent"

    if not TYPE_CHECKING:
        # The sample test marked urgent.
        sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, required=True, ondelete="cascade")
        # Why the test is urgent.
        reason = fields.Text(required=True)

    def action_mark(self):
        self.ensure_one()
        self.sample_test_id._mark_urgent(self.reason)
        return {"type": "ir.actions.act_window_close"}
