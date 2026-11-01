from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_SAMPLE_TEST_DUE_DATE_CHANGE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test_due_date_change as SampleTestDueDateChangeBase
else:
    SampleTestDueDateChangeBase = object


# Đổi Hạn Hoàn Thành Của Chỉ Tiêu Của Mẫu
class SampleTestDueDateChange(models.TransientModel, SampleTestDueDateChangeBase):
    _name = MODEL_SAMPLE_TEST_DUE_DATE_CHANGE
    _description = "Change a Sample Test's Due Date"

    if not TYPE_CHECKING:
        # The sample test whose due date changes.
        sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, required=True, ondelete="cascade")
        # The new due date.
        due_date = fields.Datetime(required=True)
        # Why the due date changes.
        reason = fields.Text(required=True)
        # True when the company's working calendar has no working time on the day of the new due date.
        due_on_non_working_day = fields.Boolean(compute="_compute_due_on_non_working_day")

    @api.depends("due_date")
    def _compute_due_on_non_working_day(self):
        tests = self.env[MODEL_SAMPLE_TEST]
        for change in self:
            change.due_on_non_working_day = bool(change.due_date) and not tests._is_working_day(change.due_date)

    def action_change(self):
        self.ensure_one()
        self.sample_test_id._change_due_date(self.due_date, self.reason)
        return {"type": "ir.actions.act_window_close"}
