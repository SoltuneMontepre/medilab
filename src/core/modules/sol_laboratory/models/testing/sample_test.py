from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RECEIVED_TRIGGER

# The statuses of a test still open for work: it can be measured, scheduled or cancelled.
OPEN_STATUSES = ("waiting", "assigned", "testing")
# The action of the testing task a received sample creates for each of its tests.
TESTING_ACTION = "test"
FINISHED_STATUSES = ("approved", "cancelled")
END_OF_DAY = time(23, 59, 59)


# Chỉ Tiêu Của Mẫu
class SampleTest(models.Model):
    _name = MODEL_SAMPLE_TEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
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
    # Results of the test, one per attempt.
    result_ids = fields.One2many(MODEL_TEST_RESULT, "sample_test_id", string="Results")
    # Why the test was cancelled, such as the parameter cannot be tested on this sample.
    cancel_reason = fields.Text(readonly=True, copy=False)
    # Head of department who cancelled the test.
    cancelled_by_id = fields.Many2one(
        MODEL_PERSON, string="Cancelled By", readonly=True, copy=False, ondelete="restrict"
    )
    # When the test was cancelled.
    cancelled_at = fields.Datetime(readonly=True, copy=False)
    # True when the due date is within the urgency threshold.
    is_urgent = fields.Boolean(string="Urgent", compute="_compute_is_urgent")
    # The parameter's subcontracted ways of testing whose subcontractor can be chosen, through which an outsourcing
    # suggestion sends the test.
    subcontracted_method_ids = fields.Many2many(
        MODEL_PARAMETER_METHOD, string="Subcontracted Ways", compute="_compute_subcontracted_method_ids"
    )
    # The subcontractor that tests it; empty when the laboratory tests it in-house.
    subcontractor_id = fields.Many2one(related="parameter_method_id.subcontractor_id")
    # Dispatches that send the test to a subcontractor.
    dispatch_ids = fields.Many2many(
        MODEL_SUBCONTRACT_DISPATCH,
        "medilab_subcontract_dispatch_test_rel",
        "sample_test_id",
        "dispatch_id",
        string="Dispatches",
        readonly=True,
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

    def write(self, vals):
        if "dispatch_ids" in vals and not self.env.su:
            raise UserError(self.env._("Add a sample test to a dispatch, or take it out, on the dispatch."))
        result = super().write(vals)
        if "parameter_method_id" in vals:
            # The tests of a dispatch go to its subcontractor, whichever side changes.
            self.sudo().dispatch_ids.filtered(lambda dispatch: dispatch.status != "cancelled")._check_sample_tests()
        return result

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
            test.subcontracted_method_ids = test.parameter_id.method_ids.filtered(
                lambda way: way.subcontractor_id._can_be_chosen()
            )

    def _compute_recommendation(self):
        bookings = self.env[MODEL_MACHINE_BOOKING]
        for test in self:
            found = None
            task = test._testing_task() if test.status in OPEN_STATUSES else None
            if task and task.assignee_id and not test.sudo().booking_ids._open():
                found = bookings._recommend(test, task.assignee_id, task.department_id)
            way, machine, start, length = found or (False, False, False, False)
            test.recommended_method_id = way
            test.recommended_machine_id = machine
            test.recommended_start = start
            test.recommended_end = start and start + length

    def _testing_task(self):
        self.ensure_one()
        return self.env[MODEL_TASK]._system_tasks_of(self, TESTING_ACTION)[:1]

    def _open_testing_task(self, department, note=False):
        """Put a testing task for the test in the queue of the department that does the work."""
        self.ensure_one()
        return self.env[MODEL_TASK]._create_for_event(
            SAMPLE_RECEIVED_TRIGGER,
            document=self,
            department=department,
            deadline=self.due_date,
            name=f"{self.sample_id.code}: {self.parameter_id.display_name}",
            note=note,
        )

    @api.model
    def _follow_assignment(self, tasks):
        """A test not started yet is assigned while its testing task has a person, and waits while it is in a queue."""
        for task in tasks.sudo().filtered(
            lambda task: task.document_model == self._name and task.action == TESTING_ACTION and task.document_id
        ):
            test = self.sudo().browse(task.document_id)
            if test.status in ("waiting", "assigned"):
                test.status = "assigned" if task.assignee_id else "waiting"

    def _tested_by(self):
        """The department of the test's latest testing task, finished or not."""
        self.ensure_one()
        domain = [("document_model", "=", self._name), ("document_id", "=", self.id), ("action", "=", TESTING_ACTION)]
        return self.env[MODEL_TASK].sudo().search(domain, order="id desc", limit=1).department_id

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

    def action_enter_result(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_TEST_RESULT,
            "views": [(False, "form")],
            "context": {"default_sample_test_id": self.id},
        }

    def _accept_outsourcing(self, way):
        """Send a test suggested for outsourcing to the subcontractor of the way of testing: it leaves the machine queue
        and joins the subcontractor's draft dispatch, which is returned."""
        self.ensure_one()
        self._check_permission("edit")
        if not self.outsourcing_suggested or self.status not in ("waiting", "assigned"):
            raise UserError(self.env._("%s is not suggested for outsourcing.", self.display_name))
        if way not in self.subcontracted_method_ids:
            raise UserError(
                self.env._(
                    "%(way)s is not a subcontracted way of testing %(test)s whose subcontractor can be chosen.",
                    way=way.display_name,
                    test=self.display_name,
                )
            )
        test = self.sudo()
        test.write({"parameter_method_id": way.id, "outsourcing_suggested": False})
        test._release_bookings()
        test._progress("outsourced")
        dispatches = self.env[MODEL_SUBCONTRACT_DISPATCH]
        dispatch = dispatches.search(
            [("subcontractor_id", "=", way.subcontractor_id.id), ("status", "=", "draft")], order="id", limit=1
        ) or dispatches.create({"subcontractor_id": way.subcontractor_id.id})
        dispatch.sample_test_ids = [Command.link(self.id)]
        return dispatch

    def action_cancel(self, reason):
        """The department doing the tests cancels them with a reason; the report leaves them out."""
        if not (reason or "").strip():
            raise UserError(self.env._("Give a reason for cancelling the test."))
        self._check_permission("edit")
        person = self.env[MODEL_PERSON]._current()
        for test in self:
            if test.status not in OPEN_STATUSES:
                raise UserError(
                    self.env._(
                        "Only a waiting, assigned or testing sample test can be cancelled: %s", test.display_name
                    )
                )
            department = test._testing_task().department_id
            if not person or not department or department != person.department_id:
                raise UserError(self.env._("Only the department testing %s can cancel it.", test.display_name))
        tests = self.sudo()
        tests.write({"cancel_reason": reason, "cancelled_by_id": person.id, "cancelled_at": fields.Datetime.now()})
        tests._cancel()

    def _cancel(self):
        tests = self.filtered(lambda test: test.status in OPEN_STATUSES)
        tests.status = "cancelled"
        self.env[MODEL_TASK]._cancel_for_document(tests, TESTING_ACTION)
        tests._release_bookings()
        tests.sample_id._follow_tests()

    def _release_bookings(self):
        """The tests leave the machines: their open bookings are cancelled and the queue gets the slots."""
        bookings = self.sudo().booking_ids._open()
        if bookings:
            bookings._set({"status": "cancelled"})
            bookings._process_queue()

    def _work_status(self):
        """The status of the test while it is worked on: by the laboratory, or by the subcontractor of its way."""
        self.ensure_one()
        return "outsourced" if self.subcontractor_id else "testing"

    def _start(self):
        """The first measurement starts the test, and with it its sample and test request."""
        self.sudo().filtered(lambda test: test.status in ("waiting", "assigned"))._progress("testing")

    def _progress(self, status):
        tests = self.sudo()
        tests.status = status
        if status == "approved":
            self.env[MODEL_TASK]._close_for_document(tests, TESTING_ACTION)
        tests.sample_id._follow_tests()

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
