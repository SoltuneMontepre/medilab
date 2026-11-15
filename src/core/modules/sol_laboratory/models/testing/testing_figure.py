from datetime import date, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.tools import SQL, date_utils

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MACHINE_BOOKING,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_SIGNATURE,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_RESULT,
    MODEL_TESTING_FIGURE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_testing_figure as TestingFigureBase
else:
    TestingFigureBase = object

# The context keys holding the first and last day of the period, as ISO dates.
PERIOD_FROM = "testing_figures_from"
PERIOD_TO = "testing_figures_to"

# One row per fact of the period: a sample test approved in it, a sample test still open past its due date at its end,
# a retest entered in it and a booking starting in it. A sample test belongs to the department of its latest testing
# task, and is approved when the last standing signature of its first approved result was recorded; a later correction
# or a report rejection leaves that approval in its period.
# ponytail: the CTEs read every task, result and signature for each read; bound them by the period if reports slow down.
QUERY = """
WITH departments AS (
    SELECT DISTINCT ON (task.document_id) task.document_id AS sample_test_id, task.department_id
      FROM medilab_task task
     WHERE task.id IN (%(testing_tasks)s)
     ORDER BY task.document_id, task.id DESC
),
approvals AS (
    SELECT result.sample_test_id, MIN(signed.at) AS approved_at
      FROM medilab_test_result result
      JOIN LATERAL (
            SELECT MAX(signature.create_date) AS at
              FROM medilab_signature signature
             WHERE signature.document_model = 'medilab.test.result'
               AND signature.document_id = result.id
               AND signature.document_version = result.document_version
               AND signature.decision = 'signed'
               AND signature.withdrawn_at IS NULL
           ) signed ON TRUE
     WHERE result.status = 'approved'
     GROUP BY result.sample_test_id
),
tests AS (
    SELECT test.id, test.status, test.due_date, test.cancelled_at, test.create_date, sample.received_at,
           department.department_id, approval.approved_at
      FROM medilab_sample_test test
      JOIN medilab_sample sample ON sample.id = test.sample_id
      LEFT JOIN departments department ON department.sample_test_id = test.id
      LEFT JOIN approvals approval ON approval.sample_test_id = test.id
)
SELECT test.id * 4 AS id, 'completed' AS kind, test.approved_at AS date, test.department_id,
       NULL::integer AS person_id, test.id AS sample_test_id, 1 AS completed,
       100.0 * (test.approved_at <= test.due_date)::int AS on_time,
       EXTRACT(EPOCH FROM test.approved_at - test.received_at) / 86400 AS turnaround_days,
       0 AS overdue, 0 AS retests, 0 AS bookings, 0.0 AS booked_hours
  FROM tests test
 WHERE test.approved_at >= %(start)s AND test.approved_at < %(end)s
UNION ALL
SELECT test.id * 4 + 1, 'overdue', test.due_date, test.department_id, NULL, test.id, 0, NULL, NULL, 1, 0, 0, 0.0
  FROM tests test
 WHERE test.due_date < %(end)s
   AND test.create_date < %(end)s
   AND (test.approved_at IS NULL OR test.approved_at >= %(end)s)
   AND NOT (test.status = 'cancelled' AND test.cancelled_at < %(end)s)
UNION ALL
SELECT result.id * 4 + 2, 'retest', result.entered_at, test.department_id, NULL, test.id, 0, NULL, NULL, 0, 1, 0, 0.0
  FROM medilab_test_result result
  JOIN tests test ON test.id = result.sample_test_id
 WHERE result.replaces_id IS NULL
   AND result.entered_at >= %(start)s AND result.entered_at < %(end)s
   AND EXISTS (
        SELECT 1
          FROM medilab_test_result earlier
         WHERE earlier.sample_test_id = result.sample_test_id
           AND earlier.replaces_id IS NULL
           AND (earlier.entered_at, earlier.id) < (result.entered_at, result.id)
       )
UNION ALL
SELECT booking.id * 4 + 3, 'booking', booking.starts_at, booking.department_id, booking.person_id,
       booking.sample_test_id, 0, NULL, NULL, 0, 0, 1, EXTRACT(EPOCH FROM booking.ends_at - booking.starts_at) / 3600
  FROM medilab_machine_booking booking
 WHERE booking.status != 'cancelled' AND booking.starts_at >= %(start)s AND booking.starts_at < %(end)s
"""


# Số Liệu Thử Nghiệm
class TestingFigure(models.Model, TestingFigureBase):
    _name = MODEL_TESTING_FIGURE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Testing Figures"
    _auto = False
    _order = "date desc, id"
    _permission_actions = ("read",)
    _depends = {
        MODEL_TASK: ["action", "department_id", "document_id", "document_model", "linked_by_system", "type_id"],
        MODEL_TASK_TYPE: ["action", "document_model", "trigger"],
        MODEL_TEST_RESULT: ["document_version", "entered_at", "replaces_id", "sample_test_id", "status"],
        MODEL_SIGNATURE: ["decision", "document_id", "document_model", "document_version", "withdrawn_at"],
        MODEL_SAMPLE_TEST: ["cancelled_at", "due_date", "sample_id", "status"],
        MODEL_SAMPLE: ["received_at"],
        MODEL_MACHINE_BOOKING: ["department_id", "ends_at", "person_id", "sample_test_id", "starts_at", "status"],
    }

    if not TYPE_CHECKING:
        # What the row counts: an approved sample test, an overdue one, a retest or a booking.
        kind = fields.Selection(
            [("completed", "Completed"), ("overdue", "Overdue"), ("retest", "Retest"), ("booking", "Booking")],
            readonly=True,
        )
        # When it happened: the approval, the due date, the retest's entry or the booking's start.
        date = fields.Datetime(readonly=True)
        # The department testing the sample test, or holding the booking.
        department_id = fields.Many2one(MODEL_DEPARTMENT, string="Department", readonly=True)
        # The person booked; empty for the other rows.
        person_id = fields.Many2one(MODEL_PERSON, string="Person", readonly=True)
        # The sample test counted.
        sample_test_id = fields.Many2one(MODEL_SAMPLE_TEST, string="Sample Test", readonly=True)
        # 1 for a sample test approved in the period.
        completed = fields.Integer(readonly=True)
        # 100 for a test approved by its due date, 0 for one approved later; averaged into the on-time share.
        on_time = fields.Float(string="On Time (%)", aggregator="avg", readonly=True)
        # Days from the sample's receipt to the test's approval; averaged.
        turnaround_days = fields.Float(string="Receipt to Approval (Days)", aggregator="avg", readonly=True)
        # 1 for a sample test neither approved nor cancelled by the end of the period, which was due before it.
        overdue = fields.Integer(readonly=True)
        # 1 for a result entered after an earlier one of the same sample test.
        retests = fields.Integer(readonly=True)
        # 1 for a booking starting in the period.
        bookings = fields.Integer(readonly=True)
        # Hours the booking holds its machine.
        booked_hours = fields.Float(readonly=True)

    @property
    def _table_sql(self):
        # The query replaces the table; Odoo's table SQL carries the _depends fields to save before reading.
        start, end = self._period_bounds()
        tasks = self.env[MODEL_TASK].sudo()
        testing_tasks = tasks._search(tasks._testing_domain()).subselect()
        return SQL(
            "(%s)",
            SQL(QUERY, start=start, end=end, testing_tasks=testing_tasks),
            to_flush=super()._table_sql._sql_tuple[2],
        )

    @api.model
    def _period(self):
        """The first and last day of the period in the context; the current month in the laboratory's time zone
        without one."""
        context = self.env.context
        if context.get(PERIOD_FROM) and context.get(PERIOD_TO):
            return date.fromisoformat(context[PERIOD_FROM]), date.fromisoformat(context[PERIOD_TO])
        return date_utils.get_month(self.env[MODEL_SAMPLE]._company_today())

    @api.model
    def _period_bounds(self):
        """The start of the period's first day and of the day after its last, in the laboratory's time zone, in UTC."""
        first, last = self._period()
        return tuple(self.env[MODEL_SAMPLE]._company_datetime(day, 0) for day in (first, last + timedelta(days=1)))
