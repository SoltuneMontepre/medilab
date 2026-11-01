from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_RESULT, MODEL_TEST_RESULT_REJECT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result_reject as TestResultRejectBase
else:
    TestResultRejectBase = object


# Từ Chối Kết Quả Thử Nghiệm
class TestResultReject(models.TransientModel, TestResultRejectBase):
    _name = MODEL_TEST_RESULT_REJECT
    _description = "Reject a Test Result"

    if not TYPE_CHECKING:
        # The result rejected.
        result_id = fields.Many2one(MODEL_TEST_RESULT, required=True, ondelete="cascade")
        # Why the result is rejected; the person who entered it receives it.
        reason = fields.Text(required=True)

    def action_reject(self):
        self.ensure_one()
        self.result_id.action_reject(self.reason)
        return {"type": "ir.actions.act_window_close"}
