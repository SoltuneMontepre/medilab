from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.tasks import FINAL_STATUSES
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES, _rooms_end

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingPlanBase
else:
    MachineBookingPlanBase = object

# A sample test the plan places has not started.
PLANNED_TEST_STATUSES = ("waiting", "assigned")


# Lịch Đặt Máy: a department's plan is its proposed bookings, which testers and heads accept.
class MachineBookingPlan(models.Model, MachineBookingPlanBase):
    _inherit = MODEL_MACHINE_BOOKING

    def _audit_scope(self):
        # A proposed slot reserves nothing and changes with every recalculation; accepting it starts its trail.
        return super()._audit_scope().filtered(lambda booking: booking.status != "proposed")

    @api.model
    def _plan(self, departments):
        """Recalculate the plans of the departments.

        Every received, not-started sample test of a department's open testing tasks without a scheduled or running
        booking has one proposed booking, for the task's assignee when there is one. The plan places them one at a time
        in priority order, each in the earliest slot by its due date where its tester, machine and rooms are free around
        the scheduled bookings and the slots placed before it. A test without such a slot keeps a proposed booking
        without a slot and is suggested for outsourcing. Scheduled bookings never move here.
        """
        # ponytail: a department's whole plan is recalculated on every change; start from the changed test if plans
        # grow long.
        tests = self.env[MODEL_SAMPLE_TEST].sudo()
        for department in departments.sudo():
            proposals = self._plan_proposals(department)
            placed = self.browse()
            for booking in proposals.sorted(lambda booking: booking.sample_test_id._plan_key(department)):
                test = booking.sample_test_id
                found = self._recommend(test, booking.person_id, department, planned=placed)
                values = {"starts_at": False, "ends_at": False}
                if found:
                    way, machine, start, length = found
                    values = {
                        "machine_id": machine.id,
                        "method_id": way.method_id.id,
                        "starts_at": start,
                        "ends_at": start + length,
                    }
                    placed |= booking
                booking._set_changed(values)
                if test.outsourcing_suggested != (not found):
                    test.outsourcing_suggested = not found
                tests |= test
            tests |= (
                self.sudo()
                .search([("department_id", "=", department.id), ("status", "in", ACTIVE_STATUSES)])
                .sample_test_id
            )
            tests |= tests.search([("at_risk", "=", True), ("booking_ids.department_id", "=", department.id)])
        tests._refresh_risk()

    @api.model
    def _plan_proposals(self, department):
        """The proposed bookings of the department's plan: one for each sample test it places, for its tester."""
        bookings = self.sudo()
        authorizations = self.env[MODEL_PARAMETER_AUTHORIZATION]
        tasks = (
            self.env[MODEL_TASK]
            .sudo()
            .search(
                self.env[MODEL_TASK]._testing_domain()
                & Domain("department_id", "=", department.id)
                & Domain("status", "not in", FINAL_STATUSES),
                order="id",
            )
        )
        planned = {}
        for task in tasks:
            test = self.env[MODEL_SAMPLE_TEST].sudo().browse(task.document_id)
            if (
                test.status not in PLANNED_TEST_STATUSES
                or test._booking_refusal()
                or test.booking_ids.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
                # Nobody is booked for a parameter they are not authorized for.
                or (task.assignee_id and not authorizations._authorized(task.assignee_id, test.parameter_id))
            ):
                continue
            planned[test] = task
        proposals = bookings.search([("status", "=", "proposed"), ("department_id", "=", department.id)], order="id")
        kept = bookings.browse()
        for booking in proposals:
            task = planned.get(booking.sample_test_id)
            if not task or booking.sample_test_id in kept.sample_test_id:
                booking._set({"status": "cancelled"})
                continue
            booking._set_changed({"task_id": task.id, "person_id": task.assignee_id.id})
            kept |= booking
        missing = [test for test in planned if test not in kept.sample_test_id]
        return kept | bookings.create(
            [
                {"sample_test_id": test.id, "task_id": planned[test].id, "person_id": planned[test].assignee_id.id}
                for test in missing
            ]
        )

    def _proposed_way(self):
        """The way of testing of a proposed booking: the test's agreed or chosen way when it uses the booking's method,
        otherwise the department's way of that method for the test's parameter and sample type, as the plan chose it."""
        self.ensure_one()
        test = self.sudo().sample_test_id
        way = test.accepted_method_id or test.parameter_method_id
        if way.method_id == self.method_id:
            return way
        return (
            self.env[MODEL_PARAMETER_METHOD]
            .sudo()
            .search(
                [
                    ("parameter_id", "=", test.parameter_id.id),
                    ("method_id", "=", self.method_id.id),
                    ("department_id", "=", self.sudo().department_id.id),
                    ("applicability_ids.sample_type_id", "=", test.sample_id.sample_type_id.id),
                ],
                limit=1,
            )
        )

    def _set_changed(self, values):
        """Write only the values that change, so recalculating an unchanged plan writes nothing."""
        self.ensure_one()
        changed = {
            name: value
            for name, value in values.items()
            if (self[name].id if self._fields[name].type == "many2one" else self[name]) != value
        }
        if changed:
            self._set(changed)

    def action_accept(self):
        """Accept proposed bookings: each reserves its tester, its machine when it needs one and its rooms together,
        or the acceptance is refused when any of them was taken meanwhile."""
        self._check_adjustable()
        for booking in self:
            if booking.status != "proposed":
                raise UserError(self.env._("Only a proposed booking can be accepted."))
            if not booking.person_id:
                raise UserError(self.env._("Assign %s to a tester before accepting its booking.", booking.display_name))
            start, end = booking.starts_at, booking.ends_at
            if not start or not end:
                raise UserError(self.env._("No machine can finish %s before its due date.", booking.display_name))
            test = booking.sudo().sample_test_id
            test._check_bookable()
            self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(booking.person_id, test.parameter_id)
            way = booking._proposed_way()
            if test.parameter_method_id != way:
                # The way's steps give the rooms the booking books.
                test.parameter_method_id = way
            rooms = self._room_steps(way)
            length = end - start
            slot = self._free_slot(
                booking.machine_id,
                length,
                booking.person_id,
                start + max(length, _rooms_end(rooms)),
                start,
                booking,
                rooms=rooms,
                way=way,
                sample=test.sample_id,
            )
            if slot != start:
                raise UserError(
                    self.env._(
                        "The slot of %s was taken meanwhile; open the plan again for its new slot.",
                        booking.display_name,
                    )
                )
            booking._set({"status": "scheduled"})
        self._plan(self.sudo().department_id)
