from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_SCOPE_LINE,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACT_DISPATCH,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
    MODEL_TEST_RESULT,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RECEIVED_TRIGGER, TESTING_ACTION
from odoo.addons.sol_laboratory.services.record_id import persisted_id

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestBase
else:
    SampleTestBase = object

# The statuses of a test still open for work: it can be measured, scheduled or cancelled.
OPEN_STATUSES = ("waiting", "assigned", "testing")
# The statuses of a sample while results can be entered for its tests.
OPEN_SAMPLE_STATUSES = ("received", "testing")
# The statuses of a sample test while a result can be entered for it: open, or sent to a subcontractor.
MEASURABLE_STATUSES = (*OPEN_STATUSES, "outsourced")
FINISHED_STATUSES = ("approved", "cancelled")


# Chỉ Tiêu Của Mẫu
class SampleTest(models.Model, SampleTestBase):
    _name = MODEL_SAMPLE_TEST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _audit_children = ("booking_ids",)
    _description = "Sample Test"
    _order = "sample_id, id"
    _rec_name = "parameter_id"
    # A sample test is cancelled, never archived or deleted.
    _permission_actions = ("read", "create", "edit")
    # The Medilab Mobile screen that opens it.
    _mobile_screen = "sample_test"

    if not TYPE_CHECKING:
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
        # The way of testing chosen for it; empty until the scheduler or the laboratory chooses.
        parameter_method_id = fields.Many2one(
            MODEL_PARAMETER_METHOD,
            string="Way of Testing",
            ondelete="restrict",
            index=True,
            domain="[('parameter_id', '=', parameter_id)]",
        )
        # True while the test's way is in-house and a line of an active certificate valid that day covers its method,
        # its parameter and its sample's type or one of that type's ancestors. Approving or cancelling the test keeps the
        # mark it had then.
        is_accredited = fields.Boolean(string="Accredited", default=False, readonly=True, copy=False)
        # The way of testing the customer accepted on the order's quotation; the test keeps to it. Empty for a test the
        # laboratory chooses the way of.
        accepted_method_id = fields.Many2one(
            MODEL_PARAMETER_METHOD, string="Accepted Way of Testing", readonly=True, ondelete="restrict"
        )
        # True when no machine can finish the test before its due date, so the scheduler suggests outsourcing it.
        outsourcing_suggested = fields.Boolean(readonly=True, copy=False, index=True)
        # Why the head of department outsourced the test straight away instead of from an outsourcing suggestion.
        emergency_outsource_reason = fields.Text(readonly=True, copy=False)
        # Machine bookings for the test.
        booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "sample_test_id", string="Bookings")
        # Results of the test, the latest entered first.
        result_ids = fields.One2many(MODEL_TEST_RESULT, "sample_test_id", string="Results")
        # Why the test was cancelled, such as the parameter cannot be tested on this sample.
        cancel_reason = fields.Text(readonly=True, copy=False)
        # Head of department who cancelled the test.
        cancelled_by_id = fields.Many2one(
            MODEL_PERSON, string="Cancelled By", readonly=True, copy=False, ondelete="restrict"
        )
        # When the test was cancelled.
        cancelled_at = fields.Datetime(readonly=True, copy=False)
        # When the test's result was first approved; empty until then, and kept when the result is sent back or
        # corrected.
        first_approved_at = fields.Datetime(readonly=True, copy=False)
        # The parameter's subcontracted ways of testing on the sample's type whose subcontractor can be chosen and is not
        # the test's customer.
        subcontracted_method_ids = fields.Many2many(
            MODEL_PARAMETER_METHOD, string="Subcontracted Ways", compute="_compute_subcontracted_method_ids"
        )
        # The subcontracted ways the test may be outsourced through, shown as the alternatives of an outsourcing
        # suggestion: those with the method the customer accepted, when there is one, since another method needs a
        # revised quotation the customer accepts.
        outsourcing_method_ids = fields.Many2many(
            MODEL_PARAMETER_METHOD, string="Agreed Subcontracted Ways", compute="_compute_subcontracted_method_ids"
        )
        # True when the current person belongs to the department of the test's testing task, which may outsource it
        # straight away.
        tested_by_my_department = fields.Boolean(compute="_compute_tested_by_my_department")
        # True when the head may move the outsourced test to another subcontractor: no dispatch holds it, such as after
        # its dispatch was cancelled.
        can_move_subcontractor = fields.Boolean(compute="_compute_can_move_subcontractor")
        # True when a result can be entered for the test now.
        can_enter_result = fields.Boolean(compute="_compute_can_enter_result")
        # The subcontractor that tests it; empty when the laboratory tests it in-house.
        subcontractor_id = fields.Many2one(related="parameter_method_id.subcontractor_id")
        # The unit results of its way of testing are expressed in on the sample's type.
        unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, compute="_compute_unit")
        # Dispatches that send the test to a subcontractor.
        dispatch_ids = fields.Many2many(
            MODEL_SUBCONTRACT_DISPATCH,
            "medilab_subcontract_dispatch_test_rel",
            "sample_test_id",
            "dispatch_id",
            string="Dispatches",
            readonly=True,
        )
        # The way of testing of the slot the department's plan proposes for the test.
        recommended_method_id = fields.Many2one(MODEL_PARAMETER_METHOD, compute="_compute_recommendation")
        # The machine of the proposed slot; empty when the way needs none.
        recommended_machine_id = fields.Many2one(MODEL_MACHINE, compute="_compute_recommendation")
        # Start of the proposed slot.
        recommended_start = fields.Datetime(compute="_compute_recommendation")
        # End of the proposed slot.
        recommended_end = fields.Datetime(compute="_compute_recommendation")

    _quantity_positive = models.Constraint("CHECK(quantity >= 1)", "A parameter is tested at least once on a sample.")

    @api.model_create_multi
    def create(self, vals_list):
        tests = super().create(vals_list)
        tests._refresh_accreditation()
        return tests

    def _document_code(self):
        """A push and Medilab Mobile name a sample test by its sample's lab code."""
        return self.sample_id.code

    def write(self, vals):
        if "dispatch_ids" in vals and not self.env.su:
            raise UserError(self.env._("Add a sample test to a dispatch, or take it out, on the dispatch."))
        if "is_accredited" in vals and not self.env.su:
            raise UserError(self.env._("Accreditation is computed from certificates; it cannot be set by hand."))
        if "accepted_method_id" in vals:
            raise UserError(self.env._("The accepted way of testing changes only through a revised quotation."))
        if vals.get("status") in FINISHED_STATUSES:
            # The mark is kept from now on, so it is worked out on the day the test is finished.
            self._refresh_accreditation()
        result = super().write(vals)
        if {"parameter_id", "parameter_method_id", "sample_id"} & set(vals):
            self._refresh_accreditation()
        if "parameter_method_id" in vals:
            # The tests of a dispatch go to its subcontractor, whichever side changes.
            self.sudo().dispatch_ids.filtered(lambda dispatch: dispatch.status != "cancelled")._check_sample_tests()
        return result

    def _refresh_accreditation(self):
        """Work out again whether the tests still open are accredited; finished tests keep their mark."""
        tests = self.sudo().filtered(lambda test: test.status not in FINISHED_STATUSES)
        keys = {
            test: (test.parameter_method_id.method_id.id, test.parameter_id.id, test.sample_id.sample_type_id.id)
            for test in tests
            if test.parameter_method_id and not test.parameter_method_id.subcontractor_id
        }
        covered = self.env[MODEL_ACCREDITATION_SCOPE_LINE]._covered(set(keys.values()))
        for accredited in (True, False):
            changed = tests.filtered(
                lambda test, accredited=accredited: (
                    (keys.get(test) in covered) == accredited and test.is_accredited != accredited
                )
            )
            if changed:
                changed.write({"is_accredited": accredited})

    @api.model
    def _finished_statuses(self):
        """The statuses in which a test keeps its accreditation mark."""
        return FINISHED_STATUSES

    @api.model
    def _refresh_accreditation_of_methods(self, methods):
        # Tests done in a way that was archived since are still open.
        self.sudo().with_context(active_test=False).search(
            [
                ("parameter_method_id.method_id", "in", methods.ids),
                ("status", "not in", FINISHED_STATUSES),
            ]
        )._refresh_accreditation()

    @api.constrains("parameter_method_id", "sample_id")
    def _check_way_applies(self):
        for test in self.filtered("parameter_method_id"):
            sample_type = test.sudo().sample_id.sample_type_id
            if not test.parameter_method_id.sudo()._applicability(sample_type):
                raise ValidationError(
                    self.env._(
                        "%(way)s does not apply to %(sample_type)s.",
                        way=test.parameter_method_id.display_name,
                        sample_type=sample_type.display_name,
                    )
                )

    @api.constrains("parameter_method_id", "accepted_method_id")
    def _check_accepted_way(self):
        # Who tests it, a department or a subcontractor, is internal; the method is what the customer accepted.
        for test in self.filtered("accepted_method_id"):
            accepted = test.accepted_method_id
            way = test.parameter_method_id
            if way.parameter_id != accepted.parameter_id or way.method_id != accepted.method_id:
                raise ValidationError(
                    self.env._(
                        "%(parameter)s is tested with %(method)s, the method the customer accepted; another method "
                        "needs a revised quotation.",
                        parameter=test.parameter_id.display_name,
                        method=accepted.method_id.display_name,
                    )
                )

    @api.constrains("parameter_method_id")
    def _check_not_outsourced_to_customer(self):
        for test in self.sudo().filtered("parameter_method_id.subcontractor_id"):
            customer = test.sample_id.request_id.customer_id
            if test.parameter_method_id._performed_by(customer.partner_id):
                raise ValidationError(
                    self.env._(
                        "%(test)s is a test of %(customer)s's own request, so it cannot go to %(customer)s as a "
                        "subcontractor.",
                        test=test.display_name,
                        customer=customer.display_name,
                    )
                )

    @api.depends("parameter_method_id", "sample_id.sample_type_id")
    def _compute_unit(self):
        for test in self:
            test.unit_id = (
                test.parameter_method_id._applicability(test.sudo().sample_id.sample_type_id).unit_id
                if test.parameter_method_id
                else False
            )

    def _compute_subcontracted_method_ids(self):
        for test in self:
            # Only ways that explicitly apply to the sample's type are offered.
            sample = test.sudo().sample_id
            customer = sample.request_id.customer_id.partner_id
            test.subcontracted_method_ids = test.parameter_id.method_ids.filtered(
                lambda way, sample=sample, customer=customer: (
                    way.subcontractor_id._can_be_chosen()
                    and bool(way._applicability(sample.sample_type_id))
                    and not way._performed_by(customer)
                )
            )
            accepted = test.accepted_method_id
            test.outsourcing_method_ids = (
                test.subcontracted_method_ids.filtered(
                    lambda way, accepted=accepted: way.method_id == accepted.method_id
                )
                if accepted
                else test.subcontracted_method_ids
            )

    @api.depends_context("uid")
    def _compute_tested_by_my_department(self):
        person = self.env[MODEL_PERSON]._current()
        for test in self:
            test.tested_by_my_department = test._tested_by_department_of(person)

    @api.depends(
        "status",
        "sample_id.status",
        "dispatch_ids.status",
        "result_ids.is_reported",
        "result_ids.status",
    )
    def _compute_can_enter_result(self):
        for test in self:
            test.can_enter_result = not test._result_refusal()

    @api.depends("status", "dispatch_ids.status")
    def _compute_can_move_subcontractor(self):
        for test in self:
            test.can_move_subcontractor = test.status == "outsourced" and not test._active_dispatches()

    def _active_dispatches(self):
        return self.sudo().dispatch_ids.filtered(lambda dispatch: dispatch.status != "cancelled")

    def _result_refusal(self):
        """Why no result can be entered for the test now; empty when one can. A test the laboratory measures takes
        results only from the person who claimed its testing task. An outsourced test takes results once its
        subcontractor received its dispatch, and its subcontractor's result waiting to be sent comes before any
        other."""
        self.ensure_one()
        test = self.sudo()
        if test.status not in MEASURABLE_STATUSES or test.sample_id.status not in OPEN_SAMPLE_STATUSES:
            return self.env._(
                "A result is entered only for a received sample while %s is waiting, assigned, in testing "
                "or outsourced.",
                test.display_name,
            )
        if test.status != "outsourced":
            assignee = test._testing_task().assignee_id
            if self.env.su or (assignee and assignee == self.env[MODEL_PERSON]._current()):
                return ""
            return self.env._("Claim the testing task of %s before entering its result.", test.display_name)
        if not test.dispatch_ids.filtered(lambda dispatch: dispatch.status == "received"):
            return self.env._(
                "%s is entered once its subcontractor received the dispatch that holds it.", test.display_name
            )
        if test.result_ids.filtered(
            lambda result: result.is_reported and result.status == STATE_NONE and result.entered_by_id.share
        ):
            return self.env._(
                "The subcontractor's result of %s waits to be sent; send it, or have it rejected, before entering "
                "another.",
                test.display_name,
            )
        return ""

    def _comparison_requested(self):
        """Whether its results are assessed against the sample's regulation: the regulation limits its parameter on some
        sample type. An empty test has none."""
        return self.parameter_id in self.sudo().sample_id.regulation_id.limit_ids.parameter_id

    def _proposed_booking(self):
        """The test's proposed booking that has a slot in its department's plan."""
        self.ensure_one()
        return self.sudo().booking_ids.filtered(
            lambda booking: booking.status == "proposed" and bool(booking.starts_at)
        )[:1]

    def _compute_recommendation(self):
        for test in self:
            proposal = test._proposed_booking() if test.status in OPEN_STATUSES else None
            if not proposal:
                test.recommended_method_id = False
                test.recommended_machine_id = False
                test.recommended_start = False
                test.recommended_end = False
                continue
            test.recommended_method_id = proposal._proposed_way()
            test.recommended_machine_id = proposal.machine_id
            test.recommended_start = proposal.starts_at
            test.recommended_end = proposal.ends_at

    def _testing_task(self):
        self.ensure_one()
        return self.env[MODEL_TASK]._system_tasks_of(self, TESTING_ACTION)[:1]

    def _open_testing_task(self, department, note: str | bool = False):
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
        for task in tasks.sudo().filtered_domain(self.env[MODEL_TASK]._testing_domain()):
            test = self.sudo().browse(task.document_id)
            if test.status in ("waiting", "assigned"):
                test.status = "assigned" if task.assignee_id else "waiting"

    def _latest_testing_task(self):
        """The test's latest testing task, finished or not."""
        self.ensure_one()
        domain = self.env[MODEL_TASK]._testing_domain() & Domain("document_id", "=", self.id)
        return self.env[MODEL_TASK].sudo().search(domain, order="id desc", limit=1)

    def _tested_by(self):
        """The department of the test's latest testing task, finished or not."""
        return self._latest_testing_task().department_id

    def _reopen_testing_task(self):
        """Give the test's latest testing task back to its assignee, or to its queue, once it was done."""
        task = self._latest_testing_task()
        if task.status == "done":
            task.write({"status": "assigned" if task.assignee_id else "open", "done_at": False})

    def action_approve_booking(self):
        """Approve the slot the department's plan proposes for each test, recalculated first. Approving needs the
        permission to edit bookings, which the head of the department has."""
        for test in self:
            task = test._testing_task()
            if test.sudo().booking_ids.filtered(lambda booking: booking.status in ("scheduled", "in_progress")):
                raise UserError(self.env._("%s is already holding a machine.", test.display_name))
            if not task.assignee_id:
                raise UserError(self.env._("Assign %s to a person before approving its booking.", test.display_name))
            self.env[MODEL_MACHINE_BOOKING]._plan(task.sudo().department_id)
            proposal = test._proposed_booking()
            if not proposal:
                raise UserError(self.env._("No machine can finish %s before its due date.", test.display_name))
            proposal.with_env(self.env).action_approve()

    def action_enter_result(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_TEST_RESULT,
            "views": [(False, "form")],
            "context": {"default_sample_test_id": self.id},
        }

    def _accept_outsourcing(self, way):
        """Send a test suggested for outsourcing to the subcontractor of the way of testing."""
        self.ensure_one()
        self._check_permission("edit")
        if not self.outsourcing_suggested or self.status not in ("waiting", "assigned"):
            raise UserError(self.env._("%s is not suggested for outsourcing.", self.display_name))
        return self._send_to_subcontractor(way)

    def _outsource_now(self, way, reason):
        """The department testing a waiting or assigned test sends it to the subcontractor of the way of testing straight
        away in an emergency, with a reason, without an outsourcing suggestion."""
        self.ensure_one()
        if not ((reason or "").strip()):
            raise UserError(self.env._("Give a reason for outsourcing the test straight away."))
        self._check_permission("edit")
        if self.status not in ("waiting", "assigned"):
            raise UserError(
                self.env._(
                    "Only a waiting or assigned sample test can be outsourced straight away: %s", self.display_name
                )
            )
        if not self._tested_by_department_of(self.env[MODEL_PERSON]._current()):
            raise UserError(
                self.env._("Only the department testing %s can outsource it straight away.", self.display_name)
            )
        return self._send_to_subcontractor(way, reason)

    def _move_to_subcontractor(self, way):
        """The head moves an outsourced test that no dispatch holds, such as after its subcontractor's accreditation
        lapsed and the dispatch was cancelled, to another subcontracted way with the same method; it joins that
        subcontractor's draft dispatch."""
        self.ensure_one()
        self._check_permission("edit")
        if not self.can_move_subcontractor:
            raise UserError(
                self.env._(
                    "Only an outsourced sample test that no dispatch holds can move to another subcontractor: %s",
                    self.display_name,
                )
            )
        return self._send_to_subcontractor(way, self.emergency_outsource_reason)

    def _tested_by_department_of(self, person):
        """True when the person belongs to the department of the test's testing task."""
        self.ensure_one()
        department = self._testing_task().department_id
        return bool(person and department and department == person.department_id)

    def _send_to_subcontractor(self, way, emergency_reason: str | bool = False):
        """The test leaves the machine queue and joins the draft dispatch to the subcontractor of the way of testing,
        which is returned. The reason is kept when the test is outsourced straight away."""
        self.ensure_one()
        if way in self.subcontracted_method_ids and way not in self.outsourcing_method_ids:
            raise UserError(
                self.env._(
                    "%(way)s tests %(test)s with another method than the one the customer accepted; outsourcing "
                    "through it needs a revised quotation the customer accepts.",
                    way=way.display_name,
                    test=self.display_name,
                )
            )
        if way not in self.outsourcing_method_ids:
            raise UserError(
                self.env._(
                    "%(way)s is not a subcontracted way of testing %(test)s whose subcontractor can be chosen for it.",
                    way=way.display_name,
                    test=self.display_name,
                )
            )
        test = self.sudo()
        test.write(
            {
                "parameter_method_id": way.id,
                "outsourcing_suggested": False,
                "emergency_outsource_reason": emergency_reason,
            }
        )
        if test.status != "outsourced":
            test._progress("outsourced")
            # Once outsourced, the test leaves its department's plan.
            test._release_bookings()
        # The subcontractor or a lab QA enters its result, so no in-house testing task stays open; the test still
        # belongs to the department of its latest testing task.
        self.env[MODEL_TASK]._cancel_for_document(test, TESTING_ACTION)
        dispatches = self.env[MODEL_SUBCONTRACT_DISPATCH]
        dispatch = dispatches.search(
            [("subcontractor_id", "=", way.subcontractor_id.id), ("status", "=", "draft")], order="id", limit=1
        ) or dispatches.create({"subcontractor_id": way.subcontractor_id.id})
        dispatch.sample_test_ids = [Command.link(persisted_id(self))]
        return dispatch

    def action_cancel(self, reason):
        """The department doing the tests cancels them with a reason; the report leaves them out."""
        if not ((reason or "").strip()):
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
            if not test._tested_by_department_of(person):
                raise UserError(self.env._("Only the department testing %s can cancel it.", test.display_name))
        tests = self.sudo()
        tests.write({"cancel_reason": reason, "cancelled_by_id": person.id, "cancelled_at": fields.Datetime.now()})
        tests._cancel()

    def _cancel(self):
        """Cancel the open tests and the outsourced ones without an approved result. A draft dispatch drops them; a
        sent or received one keeps them, shown as cancelled, and takes no more results for them."""
        tests = self.filtered(
            lambda test: (
                test.status in OPEN_STATUSES
                or test.status == "outsourced"
                or (test.status == "result_entered" and bool(test.subcontractor_id))
            )
        )
        for dispatch in tests._active_dispatches().filtered(lambda dispatch: dispatch.status == "draft"):
            dispatch.sample_test_ids = [Command.unlink(persisted_id(test)) for test in tests & dispatch.sample_test_ids]
        # A test cancelled with its sample or request has no reason of its own, but still the time it was cancelled.
        tests.filtered(lambda test: not test.cancelled_at).cancelled_at = fields.Datetime.now()
        tests.status = "cancelled"
        self.env[MODEL_TASK]._cancel_for_document(tests, TESTING_ACTION)
        tests._release_bookings()
        tests.sample_id._follow_tests()

    def _release_bookings(self):
        """The tests leave the machines: their open bookings are cancelled and their departments' plans recalculated."""
        bookings = self.sudo().booking_ids._open()
        if bookings:
            bookings._set({"status": "cancelled"})
            bookings._plan(bookings.department_id)

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
            # The first approval stays: the lab head sending the result back or a correction does not move it.
            tests.filtered(lambda test: not test.first_approved_at).first_approved_at = fields.Datetime.now()
        # Submitting the result is the tester's work done; approving it is the head's.
        if status in ("result_entered", "approved"):
            self.env[MODEL_TASK]._close_for_document(tests, TESTING_ACTION)
        tests.sample_id._follow_tests()

    def _in_use_domain(self):
        return Domain("status", "not in", FINISHED_STATUSES)
