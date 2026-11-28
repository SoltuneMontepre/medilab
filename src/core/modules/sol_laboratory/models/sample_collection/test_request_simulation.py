from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_DEPARTMENT,
    MODEL_LOCATION_UNAVAILABILITY,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PARAMETER_METHOD,
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_TYPE,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE
from odoo.addons.sol_laboratory.models.testing.machine_booking import (
    ACTIVE_STATUSES,
    HORIZON_DAYS,
    SIMULATION_PRELOAD_CONTEXT,
    RoomUse,
    SimulationPreload,
    _round_up,
    _slot_length,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestSimulationBase
else:
    TestRequestSimulationBase = object

# Statuses of a request whose samples are still to arrive while it holds its place in the laboratory's work.
HELD_REQUEST_STATUSES = ("confirmed",)


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
        input_ways = [way.sudo() for way in ways]
        departments = self.env[MODEL_DEPARTMENT].browse()
        for way in input_ways:
            departments |= way.department_id
        initial_planned, held_items = self._collect_held_work(departments, urgent, exclude)
        now = fields.Datetime.now()
        way_map = {way.id: way for _test, way, _arrival in held_items}
        for way in input_ways:
            if not way.subcontractor_id:
                way_map[way.id] = way
        arrivals = [start, now, *(arrival for _test, _way, arrival in held_items)]
        window_start = _round_up(now)
        window_end = max(arrivals) + timedelta(days=HORIZON_DAYS)
        way_resources, preload = self._build_simulation_preload(way_map, initial_planned, window_start, window_end, now)
        planned = self._place_held_items(held_items, initial_planned, way_resources, preload)
        zone_day = self.env[MODEL_SAMPLE_TEST]._local_day(start)
        finish, returned, missing = False, False, []
        for way in input_ways:
            if way.subcontractor_id:
                day = self._date_after_working_days(zone_day, way.turnaround_days)
                returned = max(returned or date.min, day)
                continue
            slot = self._place_way(
                way,
                start,
                start + timedelta(days=HORIZON_DAYS),
                planned,
                way_resources=way_resources,
                preload=preload,
            )
            if not slot:
                missing.append(way)
                continue
            planned |= slot
            finish = max(finish or slot.ends_at, slot.ends_at)
        return {"finish": finish, "returned": returned, "missing": missing}

    @api.model
    def _collect_held_work(self, departments, urgent, exclude):
        """Return proposed bookings in departments and ordered expected tests with their resolved way and arrival."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        proposed = Domain("status", "=", "proposed") & Domain("starts_at", "!=", False)
        proposed &= Domain("department_id", "in", departments.ids)
        if urgent:
            proposed &= Domain("sample_test_id.priority", "=", "urgent")
        initial_planned = bookings.search(proposed)
        tests = (
            self.env[MODEL_SAMPLE_TEST]
            .sudo()
            .search(
                Domain("sample_id.status", "=", "expected")
                & Domain("sample_id.request_id.status", "in", HELD_REQUEST_STATUSES)
                & Domain("sample_id.request_id", "not in", exclude.ids if exclude else [])
                & Domain("status", "in", ("waiting", "assigned"))
            )
        )
        tests.fetch(["accepted_method_id", "parameter_method_id", "parameter_id", "sample_id"])
        tests.sample_id.fetch(["sample_type_id", "request_id"])
        tests.sample_id.request_id.fetch(["committed_date", "priority"])
        way_cache = {}
        resolved_ways = {}
        held_tests = self.env[MODEL_SAMPLE_TEST].sudo().browse()
        for test in tests:
            sample = test.sample_id
            if urgent and not sample.request_id.priority:
                continue
            key = (
                test.accepted_method_id.id,
                test.parameter_method_id.id,
                test.parameter_id.id,
                sample.sample_type_id.id,
            )
            way = way_cache.get(key)
            if way is None:
                way = self._held_way(test)
                way_cache[key] = way
            if way.department_id in departments:
                held_tests |= test
                resolved_ways[test.id] = way
        appointments = self._collection_appointments(held_tests.sample_id.request_id)
        now = fields.Datetime.now()
        held_items = []
        for test in held_tests.sorted(lambda item: (item.sample_id.request_id.committed_date or date.max, item.id)):
            way = resolved_ways[test.id]
            if way.subcontractor_id:
                continue
            appointment = appointments.get(test.sample_id.request_id)
            arrival = appointment if isinstance(appointment, datetime) and appointment > now else now
            held_items.append((test, way, arrival))
        return initial_planned, held_items

    @api.model
    def _preload_way_resources(self, ways_rs):
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        ways_rs.fetch(
            ["parameter_id", "method_id", "department_id", "duration_minutes", "capacity", "subcontractor_id"]
        )
        ways_rs.method_id.step_ids.fetch(["sequence", "duration_minutes", "location_id"])
        ways_rs.method_id.step_ids.location_id.fetch(["is_bookable", "active"])
        auths = (
            self.env[MODEL_PARAMETER_AUTHORIZATION]
            .sudo()
            .search_fetch([("parameter_id", "in", ways_rs.parameter_id.ids)], ["parameter_id", "person_id"])
        )
        auths.person_id.fetch(["department_id", "employee_id"])
        people_by_param = defaultdict(self.env[MODEL_PERSON].sudo().browse)
        for auth in auths:
            people_by_param[auth.parameter_id.id] |= auth.person_id
        links = (
            self.env[MODEL_MACHINE_METHOD]
            .sudo()
            .search_fetch(
                [("method_id", "in", ways_rs.method_id.ids)],
                ["machine_id", "method_id", "duration_minutes", "capacity"],
            )
        )
        links_by_method = defaultdict(list)
        capacities = {}
        for link in links:
            links_by_method[link.method_id.id].append(link)
            capacities[link.machine_id.id, link.method_id.id] = link.capacity or 1
        way_resources = {}
        all_people = self.env[MODEL_PERSON].sudo().browse()
        all_machines = self.env[MODEL_MACHINE].sudo().browse()
        room_steps = []
        seen_locations = set()
        empty_machine = self.env[MODEL_MACHINE].sudo().browse()
        for way in ways_rs:
            people = people_by_param[way.parameter_id.id].filtered(
                lambda person, dept=way.department_id: person.department_id == dept
            )
            method_links = links_by_method.get(way.method_id.id, [])
            options = [(link.machine_id, link.duration_minutes) for link in method_links]
            if not method_links and way.duration_minutes:
                options.append((empty_machine, way.duration_minutes))
            rooms = bookings._room_steps(way)
            way_resources[way.id] = (people, options, rooms)
            all_people |= people
            for machine, _minutes in options:
                all_machines |= machine
            for step, offset, length in rooms:
                if step.location_id.id not in seen_locations:
                    seen_locations.add(step.location_id.id)
                    room_steps.append((step, offset, length))
        return way_resources, capacities, all_people, all_machines, room_steps

    @api.model
    def _preload_busy_bookings(self, all_machines, all_people, initial_planned, window_start, window_end):
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        if not (all_machines or all_people):
            return bookings.browse()
        holders = Domain.FALSE
        if all_machines:
            holders |= Domain("machine_id", "in", all_machines.ids)
        if all_people:
            holders |= Domain("person_id", "in", all_people.ids)
        busy = bookings.search_fetch(
            holders
            & (Domain("status", "in", ACTIVE_STATUSES) | Domain("id", "in", initial_planned.ids))
            & Domain("starts_at", "<", window_end)
            & Domain("ends_at", ">", window_start),
            ["starts_at", "ends_at", "status", "machine_id", "method_id", "person_id", "sample_test_id"],
            order="starts_at",
        )
        busy.sample_test_id.fetch(["parameter_method_id", "sample_id"])
        return busy

    @api.model
    def _preload_room_state(self, room_steps, initial_planned, window_start, window_end, now):
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        if not room_steps:
            return (
                self.env[MODEL_CALENDAR_EVENT].sudo().browse(),
                [],
                self.env[MODEL_LOCATION_UNAVAILABILITY].sudo().browse(),
            )
        location_ids = [step.location_id.id for step, _offset, _length in room_steps]
        room_events = bookings._room_bookings(room_steps, window_start, window_end)
        planned_room_uses = list(initial_planned._room_uses())
        closures = (
            self.env[MODEL_LOCATION_UNAVAILABILITY]
            .sudo()
            .search([("location_id", "in", location_ids), ("ends_at", ">", now)])
        )
        return room_events, planned_room_uses, closures

    @api.model
    def _build_simulation_preload(self, way_map, initial_planned, window_start, window_end, now):
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        if not way_map:
            empty_preload = SimulationPreload(
                window=(window_start, window_end),
                usable_until={},
                held_machines=set(),
                closures=self.env[MODEL_LOCATION_UNAVAILABILITY].sudo().browse(),
                working={},
                busy=bookings.browse(),
                unsaved_planned=[],
                capacities={},
                room_events=self.env[MODEL_CALENDAR_EVENT].sudo().browse(),
                planned_room_uses=[],
            )
            return {}, empty_preload
        ways_rs = self.env[MODEL_PARAMETER_METHOD].sudo().browse(list(way_map.keys()))
        way_resources, capacities, all_people, all_machines, room_steps = self._preload_way_resources(ways_rs)
        all_machines.fetch(["status", "active", "next_calibration_date", "next_maintenance_date"])
        all_machines.service_ids.fetch(["machine_id", "kind", "service_date", "downtime_start", "downtime_end"])
        usable_until = {machine.id: machine._usable_until() for machine in all_machines}
        held_bookings = (
            bookings.search_fetch(
                [("machine_id", "in", all_machines.ids), ("status", "=", "in_progress"), ("ends_at", "<=", now)],
                ["machine_id"],
            )
            if all_machines
            else bookings.browse()
        )
        all_people.employee_id.fetch(["resource_calendar_id", "resource_id"])
        working = {person.id: bookings._working_time(person, window_start, window_end) for person in all_people}
        busy = self._preload_busy_bookings(all_machines, all_people, initial_planned, window_start, window_end)
        room_events, planned_room_uses, closures = self._preload_room_state(
            room_steps, initial_planned, window_start, window_end, now
        )
        unsaved_planned = [
            (booking, booking.starts_at, booking.ends_at)
            for booking in initial_planned.filtered(lambda item: not item.id)
            if isinstance(booking.starts_at, datetime) and isinstance(booking.ends_at, datetime)
        ]
        preload = SimulationPreload(
            window=(window_start, window_end),
            usable_until=usable_until,
            held_machines=set(held_bookings.machine_id.ids),
            closures=closures,
            working=working,
            busy=busy,
            unsaved_planned=unsaved_planned,
            capacities=capacities,
            room_events=room_events,
            planned_room_uses=planned_room_uses,
        )
        return way_resources, preload

    @api.model
    def _place_held_items(self, held_items, planned, way_resources, preload):
        for test, way, arrival in held_items:
            slot = self._place_way(
                way,
                arrival,
                arrival + timedelta(days=HORIZON_DAYS),
                planned,
                test=test,
                way_resources=way_resources,
                preload=preload,
            )
            if slot:
                planned |= slot
        return planned

    @api.model
    def _held_bookings(self, departments, urgent, exclude):
        """The proposed bookings of the departments' plans that have a slot, and unsaved bookings placing the
        expected tests of confirmed requests in those departments, as the plan would place them once received."""
        initial_planned, held_items = self._collect_held_work(departments, urgent, exclude)
        now = fields.Datetime.now()
        way_map = {way.id: way for _test, way, _arrival in held_items}
        arrivals = [now, *(arrival for _test, _way, arrival in held_items)]
        way_resources, preload = self._build_simulation_preload(
            way_map, initial_planned, _round_up(now), max(arrivals) + timedelta(days=HORIZON_DAYS), now
        )
        return self._place_held_items(held_items, initial_planned, way_resources, preload)

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
        """The appointment of each request's open sample collection, by request."""
        if not requests:
            return {}
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
        return {requests.browse(task.document_id): task.planned_start for task in tasks}

    @api.model
    def _place_way(self, way, not_before, not_after, planned, test=None, way_resources=None, preload=None):
        """An unsaved proposed booking at the earliest end of a free slot for the way from not_before, among its
        parameter's authorized people in its department and the machines of its method, or without a machine for the
        way's own duration; an empty one when there is none."""
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        if preload is not None:
            bookings = bookings.with_context(**{SIMULATION_PRELOAD_CONTEXT: preload})
        if way_resources is not None and way.id in way_resources:
            people, options, rooms = way_resources[way.id]
        else:
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
        best_end = None
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
                if start and (best_end is None or start + length < best_end):
                    best = (person, start, length, machine)
                    best_end = start + length
        if not best:
            return bookings.browse()
        person, start, length, machine = best
        slot = bookings.new(
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
        if preload is not None:
            preload.unsaved_planned.append((slot, start, start + length))
            if rooms:
                preload.planned_room_uses.extend(
                    RoomUse(step.location_id, start + offset, start + offset + step_length, slot)
                    for step, offset, step_length in rooms
                )
        return slot
