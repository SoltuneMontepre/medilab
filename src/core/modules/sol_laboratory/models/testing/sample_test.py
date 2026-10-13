from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
)

CANCELLABLE_STATUSES = ("waiting", "assigned", "testing")
# The action of the testing task a received sample creates for each of its tests.
TESTING_ACTION = "test"
FINISHED_STATUSES = ("approved", "cancelled")
END_OF_DAY = time(23, 59, 59)


# Chỉ Tiêu Của Mẫu
class SampleTest(models.Model):
    _name = MODEL_SAMPLE_TEST
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Sample Test"
    _order = "sample_id, id"
    _rec_name = "parameter_id"
    # A sample test is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")

    # The sample tested.
    sample_id = fields.Many2one(MODEL_SAMPLE, required=True, ondelete="cascade", index=True)
    # The parameter tested.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict", index=True)
    # How many times the parameter is tested on the sample; at least 1.
    quantity = fields.Integer(required=True, default=1)
    # Where the test is in its lifecycle.
    status = fields.Selection(
        [
            ("waiting", "Waiting"),
            ("assigned", "Assigned"),
            ("testing", "Testing"),
            ("outsourced", "Outsourced"),
            ("result_entered", "Result Entered"),
            ("approved", "Approved"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="waiting",
        readonly=True,
        copy=False,
        index=True,
    )
    # When the laboratory plans to finish the test. The default is the end of the day, in the company's time zone, a
    # safety margin before the request's expected date; it can be changed, and is worked out again when that date changes.
    due_date = fields.Datetime(compute="_compute_due_date", store=True, readonly=False)
    # The way of testing chosen for it; empty until the scheduler or the laboratory chooses.
    parameter_method_id = fields.Many2one(
        MODEL_PARAMETER_METHOD,
        string="Way of Testing",
        ondelete="restrict",
        index=True,
        domain="[('parameter_id', '=', parameter_id)]",
    )
    # True when no machine can finish the test before its due date, so the scheduler suggests outsourcing it.
    outsourcing_suggested = fields.Boolean(readonly=True, copy=False, index=True)
    # Machine bookings for the test.
    booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "sample_test_id", string="Bookings")
    # True when the due date is within the urgency threshold.
    is_urgent = fields.Boolean(string="Urgent", compute="_compute_is_urgent")
    # The parameter's subcontracted ways of testing, through which an outsourcing suggestion sends the test.
    subcontracted_method_ids = fields.Many2many(
        MODEL_PARAMETER_METHOD, string="Subcontracted Ways", compute="_compute_subcontracted_method_ids"
    )
    # The way of testing the scheduler recommends to the assignee of the test's testing task.
    recommended_method_id = fields.Many2one(MODEL_PARAMETER_METHOD, compute="_compute_recommendation")
    # The machine the scheduler recommends.
    recommended_machine_id = fields.Many2one(MODEL_MACHINE, compute="_compute_recommendation")
    # Start of the free slot the scheduler recommends.
    recommended_start = fields.Datetime(compute="_compute_recommendation")
    # End of the free slot the scheduler recommends.
    recommended_end = fields.Datetime(compute="_compute_recommendation")

    _quantity_positive = models.Constraint("CHECK(quantity >= 1)", "A parameter is tested at least once on a sample.")

    @api.depends("sample_id.request_id.expected_date")
    def _compute_due_date(self):
        # The margin is read here and is not a dependency: changing it leaves due dates already stored.
        margin = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
        # The laboratory's time zone, so the due date does not depend on who saved the request.
        laboratory_tz = ZoneInfo(self.env.company.tz or "UTC")
        for test in self:
            expected = test.sample_id.request_id.expected_date
            if not expected:
                test.due_date = False
                continue
            local_end = datetime.combine(expected - timedelta(days=margin), END_OF_DAY, tzinfo=laboratory_tz)
            test.due_date = local_end.astimezone(UTC).replace(tzinfo=None)

    def _compute_is_urgent(self):
        until = self.env[MODEL_MACHINE_BOOKING]._urgent_until()
        for test in self:
            test.is_urgent = bool(test.due_date) and test.due_date <= until

    def _compute_subcontracted_method_ids(self):
        for test in self:
            test.subcontracted_method_ids = test.parameter_id.method_ids.filtered("subcontractor_id")

    def _compute_recommendation(self):
        bookings = self.env[MODEL_MACHINE_BOOKING]
        for test in self:
            task = test._testing_task()
            found = None
            if task.assignee_id and not test.sudo().booking_ids._open():
                found = bookings._recommend(test, task.assignee_id, task.department_id)
            way, machine, start, length = found or (False, False, False, False)
            test.recommended_method_id = way
            test.recommended_machine_id = machine
            test.recommended_start = start
            test.recommended_end = start and start + length

    def _testing_task(self):
        self.ensure_one()
        return self.env[MODEL_TASK]._system_tasks_of(self, TESTING_ACTION)[:1]

    def action_schedule(self):
        """Queue each test for the machine the scheduler recommends, then give the queue its slots.

        The assignee of the testing task schedules their own test; anyone else needs the permission to create bookings.
        """
        person = self.env[MODEL_PERSON]._current()
        for test in self:
            task = test._testing_task()
            if test.sudo().booking_ids._open():
                raise UserError(self.env._("%s is already waiting for or holding a machine.", test.display_name))
            if not task.assignee_id:
                raise UserError(self.env._("Assign %s to a person before scheduling it.", test.display_name))
            if not test.recommended_machine_id:
                raise UserError(self.env._("No machine can finish %s before its due date.", test.display_name))
            bookings = self.env[MODEL_MACHINE_BOOKING]
            bookings = bookings.sudo() if person and task.assignee_id == person else bookings
            bookings.create(
                {
                    "machine_id": test.recommended_machine_id.id,
                    "sample_test_id": test.id,
                    "task_id": task.id,
                    "person_id": task.assignee_id.id,
                }
            )
        self.env[MODEL_MACHINE_BOOKING]._process_queue()

    def _cancel(self):
        tests = self.filtered(lambda test: test.status in CANCELLABLE_STATUSES)
        tests.status = "cancelled"
        bookings = tests.sudo().booking_ids.filtered(lambda booking: booking.status in ("queued", "scheduled"))
        if bookings:
            bookings._set({"status": "cancelled"})
            bookings._process_queue()

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
