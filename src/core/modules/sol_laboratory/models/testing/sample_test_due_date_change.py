from datetime import datetime
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
        # What the due date check finds: a free slot, a slot that moving scheduled bookings makes free, or none.
        feasibility = fields.Selection(
            [("free", "Free Slot"), ("moves", "Needs Moves"), ("infeasible", "Cannot Be Met")],
            compute="_compute_check",
        )
        # Why the date cannot be met, or which bookings would move for it.
        check_message = fields.Text(compute="_compute_check")
        # The end of the earliest day the test can finish by, when the date cannot be met.
        earliest_feasible_date = fields.Datetime(compute="_compute_check")

    @api.depends("due_date")
    def _compute_due_on_non_working_day(self):
        tests = self.env[MODEL_SAMPLE_TEST]
        for change in self:
            change.due_on_non_working_day = bool(change.due_date) and not tests._is_working_day(change.due_date)

    @api.depends("due_date", "sample_test_id")
    def _compute_check(self):
        for change in self:
            change.feasibility = change.check_message = change.earliest_feasible_date = False
            test = change.sample_test_id
            # Only the head who changes the date reads what the department's plan holds.
            if not (change.due_date and test.can_change_due_date):
                continue
            check = test._check_due_date(change.due_date)
            if check.feasible:
                change.feasibility = "moves" if check.moves else "free"
            else:
                change.feasibility = "infeasible"
                earliest = check.earliest
                change.earliest_feasible_date = earliest if isinstance(earliest, datetime) else False
            change.check_message = test.sudo()._due_date_check_text(check)

    def action_change(self):
        self.ensure_one()
        self.sample_test_id._change_due_date(self.due_date, self.reason)
        return {"type": "ir.actions.act_window_close"}

    def action_keep_at_risk(self):
        """The head keeps a due date the laboratory cannot meet, with the reason; the test is flagged at risk."""
        self.ensure_one()
        self.sample_test_id._change_due_date(self.due_date, self.reason, keep_at_risk=True)
        return {"type": "ir.actions.act_window_close"}
