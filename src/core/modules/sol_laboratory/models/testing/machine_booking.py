import math
from datetime import UTC, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CALENDAR_EVENT,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.scheduling import (
    CALENDAR_SYNC_CONTEXT,
    CALENDAR_SYNC_TOKEN,
    SCHEDULING_CONTEXT,
    SCHEDULING_TOKEN,
)
from odoo.addons.sol_laboratory.models.testing.sample_test import OPEN_STATUSES as OPEN_TEST_STATUSES
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingBase
else:
    MachineBookingBase = object

SLOT_MINUTES = 15
ACTIVE_STATUSES = ("scheduled", "in_progress")
OPEN_STATUSES = ("queued", *ACTIVE_STATUSES)
# ponytail: a test without a due date is fitted within this many days; give it a due date to plan further ahead.
HORIZON_DAYS = 30


def _round_up(moment):
    """The first slot boundary at or after the moment."""
    hour = moment.replace(minute=0, second=0, microsecond=0)
    return hour + timedelta(minutes=math.ceil((moment - hour).total_seconds() / 60 / SLOT_MINUTES) * SLOT_MINUTES)


def _slot_length(run_minutes):
    """The run time rounded up to whole slots."""
    return timedelta(minutes=math.ceil(run_minutes / SLOT_MINUTES) * SLOT_MINUTES)


def _rooms_end(rooms):
    """How long after the test's start its last room step ends."""
    return max((offset + length for _step, offset, length in rooms), default=timedelta())


def _room_clash(start, rooms, room_busy):
    """The earliest start from which the location bookings that clash with the rooms of a test starting at start are
    over; None when every room is free."""
    ends = [
        event.stop - offset
        for step, offset, length in rooms
        for event in room_busy
        if event.location_id == step.location_id
        and event.start < start + offset + length
        and event.stop > start + offset
    ]
    return max(ends, default=None)


# Lịch Đặt Máy
class MachineBooking(models.Model, MachineBookingBase):
    _name = MODEL_MACHINE_BOOKING
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Machine Booking"
    _order = "starts_at, queued_at, id"
    # A booking is cancelled, never deleted.
    _permission_actions = ("read", "create", "edit")

    if not TYPE_CHECKING:
        # The machine booked.
        machine_id = fields.Many2one(MODEL_MACHINE, required=True, ondelete="restrict", readonly=True)
        # The sample test run on the machine.
        sample_test_id = fields.Many2one(
            MODEL_SAMPLE_TEST, required=True, ondelete="restrict", readonly=True, index=True
        )
        # The testing task the booking belongs to.
        task_id = fields.Many2one(MODEL_TASK, ondelete="restrict", readonly=True, index=True)
        # The department of the testing task, whose head sees and adjusts the booking.
        department_id = fields.Many2one(related="task_id.department_id", store=True, index=True)
        # Person who runs the test.
        person_id = fields.Many2one(MODEL_PERSON, ondelete="restrict", readonly=True)
        # Due date of the sample test, copied so the queue is ordered without a join.
        due_date = fields.Datetime(related="sample_test_id.due_date", store=True)
        # When the booking joined the machine's queue; earlier bookings come first among equally urgent ones.
        queued_at = fields.Datetime(required=True, default=fields.Datetime.now, readonly=True)
        # Start of the slot; empty while the booking waits in the queue.
        starts_at = fields.Datetime(string="Start")
        # End of the slot: the start plus the run time, rounded up to whole slots.
        ends_at = fields.Datetime(string="End", readonly=True)
        # Queued, scheduled, in progress, done or cancelled.
        status = fields.Selection(
            [
                ("queued", "Queued"),
                ("scheduled", "Scheduled"),
                ("in_progress", "In progress"),
                ("done", "Done"),
                ("cancelled", "Cancelled"),
            ],
            required=True,
            default="queued",
            readonly=True,
            index=True,
        )
        # The calendar event showing the booking on the person's schedule; empty while the booking waits in the queue.
        calendar_event_id = fields.Many2one("calendar.event", ondelete="set null", readonly=True, copy=False)
        # True when the due date is within the urgency threshold, so the booking goes first in the queue.
        is_urgent = fields.Boolean(related="sample_test_id.is_urgent")
        # Steps of the testing method of the sample test's way of testing, which the person follows.
        method_step_ids = fields.One2many(
            related="sample_test_id.parameter_method_id.method_id.step_ids", string="Method Steps"
        )
        # Calendar events booking the locations of the method's steps for this booking.
        room_event_ids = fields.One2many(MODEL_CALENDAR_EVENT, "machine_booking_id", string="Room Bookings")

    _machine_start_idx = models.Index("(machine_id, starts_at)")
    _person_start_idx = models.Index("(person_id, starts_at)")
    _queue_idx = models.Index("(machine_id, status, due_date, queued_at)")
    _calendar_event_unique = models.Constraint("UNIQUE(calendar_event_id)", "A calendar event shows one booking.")
    _slot_period = models.Constraint("CHECK(ends_at > starts_at)", "A booking ends after it starts.")
    _no_overlap = models.Constraint(
        "EXCLUDE USING gist (machine_id WITH =, tsrange(starts_at, ends_at) WITH &&) "
        "WHERE (status IN ('scheduled', 'in_progress'))",
        "The machine already has a booking at that time.",
    )

    def _auto_init(self):
        # The overlap constraint compares machines with a GiST index, which needs btree_gist.
        self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        return super()._auto_init()

    @api.depends("sample_test_id")
    def _compute_display_name(self):
        for booking in self:
            test = booking.sudo().sample_test_id
            booking.display_name = f"{test.sample_id.code}: {test.parameter_id.name}"

    @api.model
    def _urgent_until(self):
        hours = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("urgency_hours")
        return fields.Datetime.now() + timedelta(hours=hours)

    @api.model_create_multi
    def create(self, vals_list):
        bookings = super().create(vals_list)
        bookings._sync_schedule()
        return bookings

    def write(self, vals):
        if {"starts_at", "ends_at"} & set(vals) and self.env.context.get(SCHEDULING_CONTEXT) is not SCHEDULING_TOKEN:
            # People move a booking only to a slot the scheduler finds free; its length stays the run time.
            vals = dict(vals)
            vals.pop("ends_at", None)
            if "starts_at" in vals:
                start = fields.Datetime.to_datetime(vals.pop("starts_at"))
                if not start:
                    raise UserError(self.env._("Cancel the booking instead of clearing its start."))
                for booking in self:
                    booking._move(start)
            if not vals:
                return True
        result = super().write(vals)
        if {"status", "starts_at", "person_id", "machine_id"} & set(vals):
            self._sync_schedule()
        return result

    def _open(self):
        return self.filtered(lambda booking: booking.status in OPEN_STATUSES)

    def _set(self, vals):
        self.sudo().with_context(**{SCHEDULING_CONTEXT: SCHEDULING_TOKEN}).write(vals)

    def _check_adjustable(self):
        """The person who runs a booking adjusts it; anyone else needs the permission to edit it."""
        person = self.env[MODEL_PERSON]._current()
        self.filtered(lambda booking: not person or booking.person_id != person)._check_permission("edit")

    def _move(self, start):
        self.ensure_one()
        self._check_adjustable()
        if self.status != "scheduled" or not self.starts_at or not self.ends_at:
            raise UserError(self.env._("Only a scheduled booking can be moved."))
        start = _round_up(start)
        length = self.ends_at - self.starts_at
        rooms = self._room_steps(self.sample_test_id.parameter_method_id)
        until = start + max(length, _rooms_end(rooms))
        if self._free_slot(self.machine_id, length, self.person_id, until, start, self, rooms=rooms) != start:
            raise UserError(
                self.env._(
                    "%(machine)s is not free for %(booking)s at that time.",
                    machine=self.machine_id.name,
                    booking=self.display_name,
                )
            )
        self._set({"starts_at": start, "ends_at": start + length})
        self._process_queue()

    def action_cancel(self):
        self._check_adjustable()
        if any(booking.status not in ("queued", "scheduled") for booking in self):
            raise UserError(self.env._("Only a queued or scheduled booking can be cancelled."))
        self._set({"status": "cancelled"})
        self._process_queue()

    def action_start(self):
        self._check_adjustable()
        if any(booking.status != "scheduled" for booking in self):
            raise UserError(self.env._("Only a scheduled booking can be started."))
        self._set({"status": "in_progress"})
        self.sample_test_id._start()

    def action_done(self):
        self._check_adjustable()
        if any(booking.status != "in_progress" for booking in self):
            raise UserError(self.env._("Only a booking in progress can be done."))
        self._set({"status": "done"})

    def _sync_schedule(self):
        """Show each active booking on its person's calendar and as the planned time of its testing task.

        The event has no alarm: the reminder job reminds of it, as of planned tasks.
        """
        events = self.env[MODEL_CALENDAR_EVENT].sudo().with_context(**{CALENDAR_SYNC_CONTEXT: CALENDAR_SYNC_TOKEN})
        for booking in self.sudo():
            booking._sync_room_events()
            user = booking.person_id.user_id
            event = booking.calendar_event_id.with_context(**{CALENDAR_SYNC_CONTEXT: CALENDAR_SYNC_TOKEN})
            if booking.status not in ACTIVE_STATUSES or not user:
                # A done booking stays on the calendar as the time the test ran.
                if event and booking.status != "done":
                    booking._set({"calendar_event_id": False})
                    event.unlink()
                continue
            values = {
                "name": f"{booking.machine_id.name}: {booking.display_name}",
                "start": booking.starts_at,
                "stop": booking.ends_at,
                "allday": False,
                "user_id": user.id,
                "partner_ids": [Command.set(persisted_ids(user.partner_id))],
                "alarm_ids": [Command.clear()],
                "location": booking.sample_test_id.sample_id.sampling_location_id.display_name or False,
            }
            if event:
                event.write(values)
            else:
                booking._set({"calendar_event_id": events.create(values).id})
        for task in self.sudo().task_id:
            slots = task.booking_ids.filtered(lambda booking: bool(booking.status != "cancelled" and booking.starts_at))
            # Writing the planned time also drops the task's own event: the bookings' events show it.
            task.write(
                {
                    "planned_start": min(slots.mapped("starts_at"), default=False),
                    "planned_end": max(slots.mapped("ends_at"), default=False),
                }
            )

    def _sync_room_events(self):
        """Book the locations of the method's steps for the step times of an active booking, on its person's calendar.

        A queued or cancelled booking frees them; a done one keeps them as the time the steps ran.
        """
        self.ensure_one()
        events = self.room_event_ids.with_context(**{CALENDAR_SYNC_CONTEXT: CALENDAR_SYNC_TOKEN})
        if self.status not in ACTIVE_STATUSES:
            if self.status != "done":
                events.unlink()
            return
        user = self.person_id.user_id
        attendees = {"user_id": user.id, "partner_ids": [Command.set(persisted_ids(user.partner_id))]}
        planned = [
            (step, events.filtered(lambda event, step=step: event.step_id == step)[:1], self.starts_at + offset, length)
            for step, offset, length in self._room_steps(self.sample_test_id.parameter_method_id)
        ]
        (events - events.browse().union(*(event for _step, event, _begin, _length in planned))).unlink()
        # The overlap constraint checks each row as it is written: moving later, the last step moves first.
        if any(event and begin > event.start for _step, event, begin, _length in planned):
            planned.reverse()
        for step, event, begin, length in planned:
            values = {"start": begin, "stop": begin + length, "allday": False, **attendees}
            if event:
                event.write(values)
                continue
            events.create(
                {
                    **values,
                    "name": f"{step.location_id.name}: {self.display_name}",
                    "location_id": step.location_id.id,
                    "machine_booking_id": self.id,
                    "step_id": step.id,
                }
            )

    @api.model
    def _room_steps(self, way):
        """The steps of the way of testing's method done in a bookable location, as (step, offset from the test's
        start, length): steps run in step number order, each for its duration rounded up to whole slots."""
        rooms, offset = [], timedelta()
        for step in way.sudo().method_id.step_ids.sorted("sequence"):
            length = _slot_length(step.duration_minutes)
            if step.location_id.is_bookable and step.location_id.active:
                rooms.append((step, offset, length))
            offset += length
        return rooms

    @api.model
    def _process_queue(self):
        """Give each queued booking the next free slot: urgent ones first, then in the order they joined the queue.

        A booking that no machine can finish before its due date stays queued, and its test is suggested for outsourcing.
        """
        # ponytail: the whole queue is replanned on every change; plan per machine if the queue grows long.
        queued = self.sudo().search([("status", "=", "queued")])
        for booking in queued.sorted(lambda b: (not b.is_urgent, b.queued_at, b.id)):
            test = booking.sample_test_id
            found = self._recommend(test, booking.person_id, booking.department_id)
            if not found:
                test.outsourcing_suggested = True
                continue
            way, machine, start, length = found
            # The way of testing is set first: its steps give the rooms the booking books.
            test.write({"parameter_method_id": way.id, "outsourcing_suggested": False})
            booking._set(
                {"machine_id": machine.id, "starts_at": start, "ends_at": start + length, "status": "scheduled"}
            )

    @api.model
    def _requeue(self, machines):
        """Put the scheduled bookings that end after their machine stops being fit to use back in the queue, then replan
        it."""
        late = self.browse()
        for machine in machines:
            late |= self.sudo().search(
                [
                    ("machine_id", "=", machine.id),
                    ("status", "=", "scheduled"),
                    ("ends_at", ">", machine._usable_until()),
                ]
            )
        late._set({"status": "queued", "starts_at": False, "ends_at": False})
        self._process_queue()

    @api.model
    def _follow_assignment(self, tasks):
        """Hand the bookings of reassigned testing tasks over to the new assignee.

        A booking not yet running goes back to the queue for a slot in the new assignee's working time, or is cancelled
        when the task goes back to a queue. For a newly assigned test, check that a machine can finish it in time, and
        suggest outsourcing it when none can.
        """
        released = False
        for task in tasks.sudo().filtered_domain(self.env[MODEL_TASK]._testing_domain()):
            bookings = task.booking_ids._open()
            waiting = bookings.filtered(lambda booking: booking.status != "in_progress")
            (bookings - waiting)._set({"person_id": task.assignee_id.id})
            if waiting and task.assignee_id:
                waiting._set(
                    {"person_id": task.assignee_id.id, "status": "queued", "starts_at": False, "ends_at": False}
                )
            elif waiting:
                waiting._set({"status": "cancelled"})
            elif not bookings and task.assignee_id:
                test = self.env[MODEL_SAMPLE_TEST].sudo().browse(task.document_id)
                # Only an open test can be suggested for outsourcing; an outsourced one has left the machines.
                if test.status in OPEN_TEST_STATUSES:
                    test.outsourcing_suggested = not self._recommend(test, task.assignee_id, task.department_id)
            released = released or bool(waiting)
        if released:
            self._process_queue()

    @api.model
    def _recommend(self, test, person, department):
        """The way of testing, machine, start and slot length that finish the test soonest by its due date, from the
        department's ways of testing that apply to the sample's type and the machines that run them, with every
        bookable room of the way's steps free; None when no machine can."""
        now = fields.Datetime.now()
        not_after = test.due_date or now + timedelta(days=HORIZON_DAYS)
        if not_after <= now:
            return None
        in_house = (
            Domain("parameter_method_id.department_id", "=", department.id)
            if department
            else Domain("parameter_method_id.department_id", "!=", False)
        )
        links = (
            self.env[MODEL_PARAMETER_METHOD_MACHINE]
            .sudo()
            .search(
                Domain("parameter_method_id.parameter_id", "=", test.parameter_id.id)
                & Domain("parameter_method_id.active", "=", True)
                & Domain(
                    "parameter_method_id.applicability_ids.sample_type_id", "=", test.sudo().sample_id.sample_type_id.id
                )
                & in_house
            )
        )
        working = self._working_time(person, _round_up(now), not_after)
        best, best_end = None, None
        for link in links:
            length = _slot_length(link.run_minutes)
            rooms = self._room_steps(link.parameter_method_id)
            start = self._free_slot(link.machine_id, length, person, not_after, working=working, rooms=rooms)
            if start and (best_end is None or start + length < best_end):
                best, best_end = (link.parameter_method_id, link.machine_id, start, length), start + length
        return best

    @api.model
    def _free_slot(self, machine, length, person, not_after, not_before=None, ignore=None, working=None, rooms=()):
        """The earliest start of a free slot of the given length on the machine, within the person's working time.

        The slot starts on a slot boundary, not before not_before nor now, and ends by not_after while the machine is
        still fit to use. working gives the person's working intervals when the caller has them already. rooms are the
        steps done in a bookable location, from _room_steps: each location must be free for its step's time, which
        ends by not_after. Returns None when there is no such slot.
        """
        now = fields.Datetime.now()
        start_from = _round_up(max(not_before or now, now))
        limit = min(not_after, machine._usable_until())
        if start_from + length > limit:
            return None
        busy = self.sudo().search_fetch(
            Domain("machine_id", "=", machine.id)
            & Domain("status", "in", ACTIVE_STATUSES)
            & Domain("starts_at", "<", limit)
            & Domain("ends_at", ">", start_from)
            & Domain("id", "not in", ignore.ids if ignore else []),
            ["starts_at", "ends_at"],
            order="starts_at",
        )
        rooms_end = _rooms_end(rooms)
        room_busy = self._room_bookings(rooms, start_from, not_after, ignore) if rooms else []
        if working is None:
            working = self._working_time(person, start_from, limit)
        for work_start, work_end in working:
            start = _round_up(max(work_start, start_from))
            while start + length <= min(work_end, limit):
                if start + rooms_end > not_after:
                    return None
                end = start + length
                clash = next((b.ends_at for b in busy if b.starts_at < end and b.ends_at > start), None)
                clash = clash or _room_clash(start, rooms, room_busy)
                if not clash:
                    return start
                start = _round_up(clash)
        return None

    @api.model
    def _room_bookings(self, rooms, start, end, ignore=None):
        """The bookings of the rooms between start and end, except those of the ignored machine bookings."""
        return (
            self.env[MODEL_CALENDAR_EVENT]
            .sudo()
            .search_fetch(
                Domain("location_id", "in", [step.location_id.id for step, _offset, _length in rooms])
                & Domain("start", "<", end)
                & Domain("stop", ">", start)
                & Domain("machine_booking_id", "not in", ignore.ids if ignore else []),
                ["location_id", "start", "stop"],
            )
        )

    @api.model
    def _working_time(self, person, start, end):
        """The person's working intervals between start and end, as naive UTC pairs, from their working time."""
        employee = person.sudo().employee_id
        calendar = employee.resource_calendar_id or self.env.company.resource_calendar_id
        resource = employee.resource_id
        # Without a person, the working hours are placed in the laboratory's time zone.
        zone = ZoneInfo(self.env.company.tz or "UTC")
        intervals = calendar._work_intervals_batch(
            start.replace(tzinfo=UTC).astimezone(zone),
            end.replace(tzinfo=UTC).astimezone(zone),
            resource._get_resources_per_tz(),
        )[resource.id]
        return [
            (begin.astimezone(UTC).replace(tzinfo=None), finish.astimezone(UTC).replace(tzinfo=None))
            for begin, finish, _meta in intervals
        ]
