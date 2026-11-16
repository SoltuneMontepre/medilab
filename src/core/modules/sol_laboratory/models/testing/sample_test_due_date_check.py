from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, NamedTuple

from odoo import fields, models
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import MODEL_LOCATION, MODEL_MACHINE_BOOKING, MODEL_SAMPLE_TEST
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES, HORIZON_DAYS, _rooms_end

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestDueDateCheckBase
else:
    SampleTestDueDateCheckBase = object


class Slot(NamedTuple):
    """Where a sample test would be measured: its way of testing, machine (empty without one) and interval."""

    way: object
    machine: object
    start: datetime
    length: timedelta

    @property
    def end(self):
        return self.start + self.length


class DueDateCheck(NamedTuple):
    """What the due date check finds for one date."""

    feasible: bool
    # The scheduled bookings that would move to make room, as (booking, new start, new end).
    moves: list
    # Why the date cannot be met; empty when it can.
    reasons: list
    # The end of the earliest day the test can finish by; empty when it cannot within the planning horizon.
    earliest: datetime | bool


# Chỉ Tiêu Của Mẫu: the check of a due date against the resources of the department testing it.
class SampleTestDueDateCheck(models.Model, SampleTestDueDateCheckBase):
    _inherit = MODEL_SAMPLE_TEST

    def _check_due_date(self, due_date):
        """Whether the laboratory can finish the test by the due date: a free slot of its agreed way with its tester,
        its machine when the way needs one and every room of its steps, or one that moving the department's scheduled
        bookings that have not started makes free while each of them still finishes by its own due date. When it
        cannot, why not and the earliest end of a day it can. The check only reads: nothing is booked or moved."""
        self.ensure_one()
        test = self.sudo()
        if test.status == "outsourced":
            # The subcontractor's turnaround is not simulated here.
            return DueDateCheck(True, [], [], False)
        slot, moves, blocker = test._simulate_finish(due_date)
        if slot:
            return DueDateCheck(True, moves, [], False)
        return DueDateCheck(False, [], test._unmet_reasons(due_date, blocker), test._earliest_feasible_date())

    def _simulate_finish(self, due_date):
        """The slot that lets the test finish by the due date, the bookings that would move for it and the booking
        whose own due date a move would miss, when that stopped the simulation; no slot when none is found. The moves
        are worked out on unsaved bookings, so nothing real changes."""
        self.ensure_one()
        test = self.sudo()
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        person = test._testing_task().assignee_id
        department = test._testing_department()
        scheduled = test.booking_ids.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
        if scheduled:
            booking = scheduled[:1]
            held = Slot(
                test.parameter_method_id, booking.machine_id, booking.starts_at, booking.ends_at - booking.starts_at
            )
            if held.end <= due_date:
                return held, [], None
            if "in_progress" in scheduled.mapped("status"):
                # A measurement that started never moves.
                return None, [], None
        # The test's own scheduled booking that ends too late moves with it.
        found = bookings._recommend(test, person, department, due_date=due_date, ignore=scheduled)
        if found:
            slot = Slot(*found)
            return slot, [(booking, slot.start, slot.end) for booking in scheduled], None
        movable = test._movable_bookings(department, scheduled)
        found = movable and bookings._recommend(test, person, department, due_date=due_date, ignore=scheduled | movable)
        if not found:
            return None, [], None
        slot = Slot(*found)
        in_the_way = test._bookings_in_the_way(slot, person, movable, scheduled)
        if in_the_way is None:
            return None, [], None
        # ponytail: one candidate slot, the earliest with every movable booking out of the way; try the next slots when
        # a smaller set of moves would keep every due date.
        planned = bookings.new(test._unsaved_booking(slot, person))
        moves = []
        for booking in in_the_way.sorted(lambda booking: booking.sample_test_id._plan_key(department)):
            moved_test = booking.sample_test_id
            placed = bookings._recommend(
                moved_test, booking.person_id, department, planned=planned, ignore=scheduled | movable
            )
            if not placed:
                return None, [], booking
            new_slot = Slot(*placed)
            planned |= bookings.new(moved_test._unsaved_booking(new_slot, booking.person_id))
            moves.append((booking, new_slot.start, new_slot.end))
        return slot, moves, None

    def _movable_bookings(self, department, own):
        """The department's scheduled bookings that have not started, other than the test's own."""
        if not department:
            return self.env[MODEL_MACHINE_BOOKING].browse()
        return (
            self.env[MODEL_MACHINE_BOOKING]
            .sudo()
            .search(
                [
                    ("department_id", "=", department.id),
                    ("status", "=", "scheduled"),
                    ("starts_at", ">", fields.Datetime.now()),
                    ("id", "not in", own.ids),
                ]
            )
        )

    def _bookings_in_the_way(self, slot, person, movable, own):
        """The fewest movable bookings, in start order, whose removal frees the slot; None when removing them all does
        not."""
        self.ensure_one()
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        rooms = bookings._room_steps(slot.way)
        locations = self.env[MODEL_LOCATION].browse([step.location_id.id for step, _offset, _length in rooms])
        until = slot.start + max(slot.length, _rooms_end(rooms))
        sample = self.sample_id

        def is_free(moved):
            found = bookings._free_slot(
                slot.machine,
                slot.length,
                person,
                until,
                slot.start,
                own | moved,
                rooms=rooms,
                way=slot.way,
                sample=sample,
            )
            return found == slot.start

        candidates = movable.filtered(
            lambda booking: (
                booking.starts_at < until
                and booking.ends_at > slot.start
                and (
                    (slot.machine and booking.machine_id == slot.machine)
                    or (person and booking.person_id == person)
                    or booking.room_event_ids.location_id & locations
                )
            )
        ).sorted("starts_at")
        moved = bookings.browse()
        for booking in candidates:
            if is_free(moved):
                break
            moved |= booking
        return moved if is_free(moved) else None

    def _unsaved_booking(self, slot, person):
        """The values of an unsaved proposed booking that holds the slot while the check places other bookings."""
        self.ensure_one()
        return {
            "sample_test_id": self.id,
            "task_id": self._testing_task().id,
            "person_id": person.id,
            "machine_id": slot.machine.id,
            "method_id": slot.way.method_id.id,
            "starts_at": slot.start,
            "ends_at": slot.end,
            "status": "proposed",
        }

    def _unmet_reasons(self, due_date, blocker):
        """Why the test cannot finish by the due date, one sentence each."""
        self.ensure_one()
        test = self.sudo()
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        now = fields.Datetime.now()
        zone = self.env.company.tz or "UTC"

        def moment(value):
            return format_datetime(self.env, value, tz=zone)

        if due_date <= now:
            return [self.env._("%s has already passed.", moment(due_date))]
        running = test.booking_ids.filtered(lambda booking: booking.status == "in_progress")
        if running:
            return [
                self.env._(
                    "The measurement in progress is planned to end %s, after the due date.",
                    moment(max(running.mapped("ends_at"))),
                )
            ]
        person = test._testing_task().assignee_id
        department = test._testing_department()
        scheduled = test.booking_ids.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
        horizon = now + timedelta(days=HORIZON_DAYS)
        reasons = []
        found = bookings._recommend(test, person, department, due_date=horizon, ignore=scheduled)
        if found:
            slot = Slot(*found)
            reasons.append(
                self.env._(
                    "The earliest free slot, on %(resource)s, ends %(end)s, after the due date.",
                    resource=slot.machine.name or slot.way.display_name,
                    end=moment(slot.end),
                )
            )
        else:
            reasons.append(
                self.env._("No machine, tester and room are free to test it within the next %s days.", HORIZON_DAYS)
            )
        if person and bookings._recommend(test, person.browse(), department, due_date=due_date, ignore=scheduled):
            reasons.append(
                self.env._(
                    "%s is not free before the due date: booked, on leave or outside working hours.",
                    person.display_name,
                )
            )
        if blocker:
            reasons.append(self.env._("Moving %s to make room would pass its own due date.", blocker.display_name))
        return reasons

    def _earliest_feasible_date(self):
        """The end of the earliest day, in the laboratory's time zone, by which the test can finish through a free slot
        or simulated moves; False when it cannot within the planning horizon."""
        self.ensure_one()
        test = self.sudo()
        bookings = self.env[MODEL_MACHINE_BOOKING].sudo()
        horizon = fields.Datetime.now() + timedelta(days=HORIZON_DAYS)
        latest = test._simulate_finish(horizon)[0]
        if not latest:
            return False
        person = test._testing_task().assignee_id
        department = test._testing_department()
        scheduled = test.booking_ids.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
        # No day is earlier than the one the test finishes on when every scheduled booking of the department moves.
        best = bookings._recommend(
            test,
            person,
            department,
            due_date=horizon,
            ignore=scheduled | test._movable_bookings(department, scheduled),
        )
        low, high = (
            self._local_day(Slot(*best).end if best else latest.end).toordinal(),
            self._local_day(latest.end).toordinal(),
        )
        while low < high:
            middle = (low + high) // 2
            if test._simulate_finish(self._end_of_day(date.fromordinal(middle)))[0]:
                high = middle
            else:
                low = middle + 1
        return self._end_of_day(date.fromordinal(high))

    def _unmet_message(self, check):
        """The refusal of a date the laboratory cannot meet: why, and the earliest date it can."""
        self.ensure_one()
        earliest = (
            format_datetime(self.env, check.earliest, tz=self.env.company.tz or "UTC")
            if check.earliest
            else self.env._("none within the next %s days", HORIZON_DAYS)
        )
        return self.env._(
            "The laboratory cannot meet this due date:\n%(reasons)s\nThe earliest feasible date is %(earliest)s. "
            "Keep the date at risk, or choose another.",
            reasons=self._due_date_check_text(check),
            earliest=earliest,
        )

    def _due_date_check_text(self, check):
        """What the check says to the head, one line each: why the date cannot be met, or which bookings would move."""
        self.ensure_one()
        zone = self.env.company.tz or "UTC"
        lines = list(check.reasons)
        lines += [
            self.env._(
                "%(booking)s would move to %(start)s.",
                booking=booking.display_name,
                start=format_datetime(self.env, start, tz=zone),
            )
            for booking, start, _end in check.moves
        ]
        return "\n".join(lines)
