from datetime import date, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.models.testing.machine_booking import HORIZON_DAYS, _slot_length

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestSimulationBase
else:
    TestRequestSimulationBase = object

# Statuses of a request whose samples are still to arrive while it holds its place in the laboratory's work.
HELD_REQUEST_STATUSES = ("confirmed", "paid", "on_credit")


# Yêu Cầu Thử Nghiệm: the simulation of new work on the laboratory's resources, behind the work it holds already. It
# only reads: nothing is booked.
class TestRequestSimulation(models.Model, TestRequestSimulationBase):
    _inherit = MODEL_TEST_REQUEST

    @api.model
    def _simulate_ways(self, ways, start, urgent=False, exclude=None):
        """Place one test for each way of testing in the list, in order, from start, on the people authorized for its
        parameter in its department, the machines of its method and the rooms of its steps. They come after the work
        the laboratory holds: scheduled and running bookings, the plans' proposed bookings and the expected tests of
        confirmed requests whose samples have not arrived, from their collection appointment, in committed date order.
        Urgent work comes after urgent work only. exclude are requests left out of the held work. Returns the latest
        in-house finish, the latest subcontracted return date, each False when there is none, and the ways no free slot
        was found for within the planning horizon."""
        departments = self.env[MODEL_DEPARTMENT].browse()
        for way in ways:
            departments |= way.sudo().department_id
        planned = self._held_bookings(departments, urgent, exclude)
        zone_day = self.env[MODEL_SAMPLE_TEST]._local_day(start)
        finish, returned, missing = False, False, []
        for way in ways:
            way = way.sudo()
            if way.subcontractor_id:
                day = self._date_after_working_days(zone_day, way.turnaround_days)
                returned = max(returned or date.min, day)
                continue
            slot = self._place_way(way, start, start + timedelta(days=HORIZON_DAYS), planned)
            if not slot:
                missing.append(way)
                continue
            planned |= slot
            finish = max(finish or slot.ends_at, slot.ends_at)
        return {"finish": finish, "returned": returned, "missing": missing}

    @api.model
    def _held_bookings(self, departments, urgent, exclude):
        """The proposed bookings of the departments' plans that have a slot, and unsaved bookings placing the
        expected tests of confirmed requests in those departments, as the plan would place them once received."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        proposed = Domain("status", "=", "proposed") & Domain("starts_at", "!=", False)
        proposed &= Domain("department_id", "in", departments.ids)
        if urgent:
            proposed &= Domain("sample_test_id.priority", "=", "urgent")
        planned = bookings.search(proposed)
        tests = (
            self.env[MODEL_SAMPLE_TEST]
            .sudo()
            .search(
                Domain("sample_id.status", "=", "expected")
                & Domain("sample_id.request_id.status", "in", HELD_REQUEST_STATUSES)
                & Domain("sample_id.request_id", "not in", exclude.ids if exclude else [])
                & Domain("status", "in", ("waiting", "assigned"))
            )
            .filtered(lambda test: self._held_way(test).department_id in departments)
        )
        if urgent:
            tests = tests.filtered(lambda test: test.sample_id.request_id.priority)
        appointments = self._collection_appointments(tests.sample_id.request_id)
        now = fields.Datetime.now()
        for test in tests.sorted(lambda test: (test.sample_id.request_id.committed_date or date.max, test.id)):
            way = test.accepted_method_id or test.parameter_method_id
            if way.subcontractor_id:
                continue
            arrival = max(appointments.get(test.sample_id.request_id.id) or now, now)
            slot = self._place_way(way, arrival, arrival + timedelta(days=HORIZON_DAYS), planned, test=test)
            if slot:
                planned |= slot
        return planned

    @api.model
    def _held_way(self, test):
        """The way an expected test will be tested by: the one the customer accepted, the one chosen, or the default way
        of its parameter on the sample's type."""
        return (
            test.accepted_method_id
            or test.parameter_method_id
            or test.parameter_id._default_way(test.sample_id.sample_type_id)
        )

    @api.model
    def _collection_appointments(self, requests):
        """The appointment of each request's open sample collection, by request id."""
        task_type = self.env[MODEL_TASK_TYPE].sudo().search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1)
        tasks = (
            self.env[MODEL_TASK]
            .sudo()
            .search(
                Domain("type_id", "=", task_type.id)
                & Domain("document_model", "=", MODEL_TEST_REQUEST)
                & Domain("document_id", "in", requests.ids)
                & Domain("status", "in", ("open", "assigned", "in_progress"))
                & Domain("planned_start", "!=", False)
            )
        )
        return {task.document_id: task.planned_start for task in tasks}

    @api.model
    def _place_way(self, way, not_before, not_after, planned, test=None):
        """An unsaved proposed booking at the earliest end of a free slot for the way from not_before, among its
        parameter's authorized people in its department and the machines of its method, or without a machine for the
        way's own duration; an empty one when there is none."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        people = (
            self.env[MODEL_PARAMETER_AUTHORIZATION]
            .sudo()
            .search([("parameter_id", "=", way.parameter_id.id)])
            .person_id.filtered(lambda person: person.department_id == way.department_id)
        )
        links = self.env[MODEL_MACHINE_METHOD].sudo().search([("method_id", "=", way.method_id.id)])
        options = [(link.machine_id, link.duration_minutes) for link in links]
        if not links and way.duration_minutes:
            options.append((links.machine_id.browse(), way.duration_minutes))
        rooms = bookings._room_steps(way)
        sample = test.sample_id if test else self.env[MODEL_SAMPLE].browse()
        best = None
        for person in people:
            for machine, minutes in options:
                length = _slot_length(minutes)
                # New work has no sample yet to count against a shared interval's capacity, so it shares none.
                start = bookings._free_slot(
                    machine,
                    length,
                    person,
                    not_after,
                    not_before=not_before,
                    rooms=rooms,
                    way=way if test else None,
                    sample=sample,
                    planned=planned,
                )
                if start and (best is None or start + length < best[1] + best[2]):
                    best = (person, start, length, machine)
        if not best:
            return bookings.browse()
        person, start, length, machine = best
        return bookings.new(
            {
                "sample_test_id": test.id if test else False,
                "person_id": person.id,
                "machine_id": machine.id,
                "method_id": way.method_id.id,
                "starts_at": start,
                "ends_at": start + length,
                "status": "proposed",
            }
        )
