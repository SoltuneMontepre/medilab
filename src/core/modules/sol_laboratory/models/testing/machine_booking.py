import math
from datetime import UTC, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CALENDAR_EVENT,
    MODEL_DOCUMENT_LOCK,
    MODEL_LOCK_MIXIN,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_METHOD,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TESTING_METHOD,
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
# A done booking keeps its interval, so the bookings that shared it still do.
SHARING_STATUSES = (*ACTIVE_STATUSES, "done")
OPEN_STATUSES = ("queued", *ACTIVE_STATUSES)
# ponytail: a test without a due date is fitted within this many days; give it a due date to plan further ahead.
HORIZON_DAYS = 30


def _round_up(moment):
    """The first slot boundary at or after the moment."""
    hour = moment.replace(minute=0, second=0, microsecond=0)
    return hour + timedelta(minutes=math.ceil((moment - hour).total_seconds() / 60 / SLOT_MINUTES) * SLOT_MINUTES)


def _slot_length(minutes):
    """The duration rounded up to whole slots."""
    return timedelta(minutes=math.ceil(minutes / SLOT_MINUTES) * SLOT_MINUTES)


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
        # The machine booked; empty when the way of the sample test needs no machine.
        machine_id = fields.Many2one(MODEL_MACHINE, ondelete="restrict", readonly=True)
        # The sample test booked.
        sample_test_id = fields.Many2one(
            MODEL_SAMPLE_TEST, required=True, ondelete="restrict", readonly=True, index=True
        )
        # The testing method of the sample test's way, stored for the shared-interval constraints.
        method_id = fields.Many2one(MODEL_TESTING_METHOD, ondelete="restrict", readonly=True, string="Testing Method")
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
        # End of the slot: the start plus the duration, rounded up to whole slots.
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
    # Bookings overlap on a machine only when they share its interval: the same method, start and end.
    _machine_one_method = models.Constraint(
        "EXCLUDE USING gist (machine_id WITH =, method_id WITH <>, tsrange(starts_at, ends_at) WITH &&) "
        "WHERE (status IN ('scheduled', 'in_progress'))",
        "The machine already runs another testing method at that time.",
    )
    _machine_same_start = models.Constraint(
        "EXCLUDE USING gist (machine_id WITH =, starts_at WITH <>, tsrange(starts_at, ends_at) WITH &&) "
        "WHERE (status IN ('scheduled', 'in_progress'))",
        "The machine already has a booking at that time.",
    )
    _machine_same_end = models.Constraint(
        "EXCLUDE USING gist (machine_id WITH =, ends_at WITH <>, tsrange(starts_at, ends_at) WITH &&) "
        "WHERE (status IN ('scheduled', 'in_progress'))",
        "The machine already has a booking at that time.",
    )

    def _auto_init(self):
        # The overlap constraints compare machines with a GiST index, which needs btree_gist.
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

    @api.constrains("starts_at", "machine_id")
    def _check_shared_interval(self):
        now = fields.Datetime.now()
        placed = self.filtered(lambda booking: booking.status in ACTIVE_STATUSES)
        if placed.machine_id:
            # Two transactions do not see each other's bookings, so each could take the last place of an interval.
            # Writing the machine row makes the later one fail on a concurrent update, which retries its request.
            # ponytail: bookings without a machine are not serialized; lock their person the same way if they race.
            self.env.cr.execute(
                SQL(
                    "UPDATE %s SET write_date = write_date WHERE id IN %s",
                    SQL.identifier(self.env[MODEL_MACHINE]._table),
                    tuple(placed.machine_id.ids),
                )
            )
        for booking in placed:
            sharing = booking._sharing().filtered(lambda other: other.status in ACTIVE_STATUSES)
            if not sharing or not booking.starts_at:
                continue
            if booking.starts_at <= now or "in_progress" in sharing.mapped("status"):
                raise ValidationError(self.env._("%s cannot join an interval that has started.", booking.display_name))
            capacity = self._capacity(booking.machine_id, booking.sample_test_id.parameter_method_id)
            if len((booking | sharing).sample_test_id.sample_id) > capacity:
                raise ValidationError(
                    self.env._(
                        "The interval of %(booking)s is full: it holds %(capacity)s samples.",
                        booking=booking.display_name,
                        capacity=capacity,
                    )
                )

    @api.model_create_multi
    def create(self, vals_list):
        tests = self.env[MODEL_SAMPLE_TEST].sudo()
        for vals in vals_list:
            if "method_id" not in vals and vals.get("sample_test_id"):
                vals["method_id"] = tests.browse(vals["sample_test_id"]).parameter_method_id.method_id.id
        bookings = super().create(vals_list)
        bookings._sync_schedule()
        return bookings

    def write(self, vals):
        if {"starts_at", "ends_at"} & set(vals) and self.env.context.get(SCHEDULING_CONTEXT) is not SCHEDULING_TOKEN:
            # People move a booking only to a slot the scheduler finds free; its length stays the duration.
            vals = dict(vals)
            vals.pop("ends_at", None)
            # A move skips the lock mixin's write, so it checks and releases the edit lock itself.
            locks = self.env[MODEL_DOCUMENT_LOCK] if self.env.su else self._check_lock()
            if "starts_at" in vals:
                start = fields.Datetime.to_datetime(vals.pop("starts_at"))
                if not start:
                    raise UserError(self.env._("Cancel the booking instead of clearing its start."))
                for booking in self:
                    booking._move(start)
            if not vals:
                if locks:
                    locks._own_edits()._release("saved")
                return True
        moving = bool({"status", "starts_at", "person_id", "machine_id"} & set(vals))
        left = self.browse().union(*(booking._sharing() for booking in self)) - self if moving else self.browse()
        result = super().write(vals)
        if moving:
            self._sync_schedule()
            # The bookings left in a shared interval book the rooms again that a leaving booking held for them.
            for booking in left:
                booking._sync_room_events()
        return result

    @api.model
    def _edits_in_views(self):
        # A person moves their own bookings without the edit permission; _move refuses anyone else's.
        return super()._edits_in_views() or bool(self.env[MODEL_PERSON]._current())

    def _open(self):
        return self.filtered(lambda booking: booking.status in OPEN_STATUSES)

    def _set(self, vals):
        self.sudo().with_context(**{SCHEDULING_CONTEXT: SCHEDULING_TOKEN}).write(vals)

    def _sharing(self):
        """The other bookings in the interval of an active booking: on its machine, or without one for its person and
        way of testing, with the same method, start and end."""
        self.ensure_one()
        if self.status not in ACTIVE_STATUSES:
            return self.browse()
        domain = (
            Domain("id", "!=", self.id)
            & Domain("status", "in", SHARING_STATUSES)
            & Domain("starts_at", "=", self.starts_at)
            & Domain("ends_at", "=", self.ends_at)
            & Domain("method_id", "=", self.method_id.id)
        )
        if self.machine_id:
            domain &= Domain("machine_id", "=", self.machine_id.id)
        else:
            domain &= (
                Domain("machine_id", "=", False)
                & Domain("person_id", "=", self.person_id.id)
                & Domain("sample_test_id.parameter_method_id", "=", self.sample_test_id.parameter_method_id.id)
            )
        return self.sudo().search(domain)

    @api.model
    def _capacity(self, machine, way):
        """The samples one interval holds for bookings of the way of testing: on the machine, from its link to the way's
        method, or without a machine, from the way."""
        if not machine:
            return way.capacity
        link = (
            self.env[MODEL_MACHINE_METHOD]
            .sudo()
            .search([("machine_id", "=", machine.id), ("method_id", "=", way.method_id.id)], limit=1)
        )
        return link.capacity or 1

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
        way = self.sample_test_id.parameter_method_id
        rooms = self._room_steps(way)
        until = start + max(length, _rooms_end(rooms))
        sample = self.sample_test_id.sample_id
        slot = self._free_slot(
            self.machine_id, length, self.person_id, until, start, self, rooms=rooms, way=way, sample=sample
        )
        if slot != start:
            raise UserError(
                self.env._(
                    "%(machine)s is not free for %(booking)s at that time.",
                    machine=self.machine_id.name or self.person_id.name,
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
                "name": f"{booking.machine_id.name}: {booking.display_name}"
                if booking.machine_id
                else booking.display_name,
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

        A queued or cancelled booking frees them; a done one keeps them as the time the steps ran. Bookings sharing an
        interval book each room once, so a booking leaves the steps another one of them holds.
        """
        self.ensure_one()
        events = self.room_event_ids.with_context(**{CALENDAR_SYNC_CONTEXT: CALENDAR_SYNC_TOKEN})
        if self.status not in ACTIVE_STATUSES:
            if self.status != "done":
                events.unlink()
            return
        user = self.person_id.user_id
        attendees = {"user_id": user.id, "partner_ids": [Command.set(persisted_ids(user.partner_id))]}
        held = self._sharing().room_event_ids.step_id
        planned = [
            (step, events.filtered(lambda event, step=step: event.step_id == step)[:1], self.starts_at + offset, length)
            for step, offset, length in self._room_steps(self.sample_test_id.parameter_method_id)
            if step not in held
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
                {
                    "machine_id": machine.id,
                    "method_id": way.method_id.id,
                    "starts_at": start,
                    "ends_at": start + length,
                    "status": "scheduled",
                }
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
        department's ways of testing that apply to the sample's type, or only the way the customer accepted: on each
        machine linked to the way's method, or without a machine for the way's own duration when the method has none,
        with every bookable room of the way's steps free; None when there is no such slot."""
        now = fields.Datetime.now()
        not_after = test.due_date or now + timedelta(days=HORIZON_DAYS)
        if not_after <= now:
            return None
        sample = test.sudo().sample_id
        domain = Domain("parameter_id", "=", test.parameter_id.id) & Domain(
            "applicability_ids.sample_type_id", "=", sample.sample_type_id.id
        )
        domain &= Domain("department_id", "=", department.id) if department else Domain("department_id", "!=", False)
        if test.accepted_method_id:
            domain &= Domain("id", "=", test.accepted_method_id.id)
        # A retest runs by the testing method of the earlier measurement.
        measured = test.sudo().result_ids.booking_id.method_id
        if measured:
            domain &= Domain("method_id", "in", measured.ids)
        ways = self.env[MODEL_PARAMETER_METHOD].sudo().search(domain)
        links = self.env[MODEL_MACHINE_METHOD].sudo().search([("method_id", "in", ways.method_id.ids)])
        # Links come in machine order, so of two machines that finish together the first one wins.
        options = [
            (way, link.machine_id, link.duration_minutes)
            for link in links
            for way in ways
            if way.method_id == link.method_id
        ]
        options += [
            (way, links.machine_id.browse(), way.duration_minutes)
            for way in ways
            if way.duration_minutes and way.method_id not in links.method_id
        ]
        working = self._working_time(person, _round_up(now), not_after)
        best, best_end = None, None
        for way, machine, minutes in options:
            length = _slot_length(minutes)
            rooms = self._room_steps(way)
            start = self._free_slot(
                machine, length, person, not_after, working=working, rooms=rooms, way=way, sample=sample
            )
            if start and (best_end is None or start + length < best_end):
                best, best_end = (way, machine, start, length), start + length
        return best

    @api.model
    def _free_slot(
        self,
        machine,
        length,
        person,
        not_after,
        not_before=None,
        ignore=None,
        working=None,
        rooms=(),
        way=None,
        sample=None,
    ):
        """The earliest start of a free slot of the given length on the machine, or without a machine when it is empty,
        within the person's working time and clear of their other bookings.

        The slot starts on a slot boundary, not before not_before nor now, and ends by not_after while the machine is
        still fit to use. working gives the person's working intervals when the caller has them already. rooms are the
        steps done in a bookable location, from _room_steps: each location must be free for its step's time, which
        ends by not_after. With the way of testing and the sample, the slot may be an interval of the same method, start
        and end that has not started and has a place for the sample. Returns None when there is no such slot.
        """
        now = fields.Datetime.now()
        start_from = _round_up(max(not_before or now, now))
        limit = min(not_after, machine._usable_until()) if machine else not_after
        if start_from + length > limit:
            return None
        holders = Domain.FALSE
        if machine:
            holders |= Domain("machine_id", "=", machine.id)
        if person:
            holders |= Domain("person_id", "=", person.id)
        busy = self.sudo().search_fetch(
            holders
            & Domain("status", "in", ACTIVE_STATUSES)
            & Domain("starts_at", "<", limit)
            & Domain("ends_at", ">", start_from)
            & Domain("id", "not in", ignore.ids if ignore else []),
            ["starts_at", "ends_at", "status", "machine_id", "method_id", "person_id", "sample_test_id"],
            order="starts_at",
        )
        spans = [
            (booking, booking.starts_at, booking.ends_at) for booking in busy if booking.starts_at and booking.ends_at
        ]
        capacity = self._capacity(machine, way) if way else 0

        def shares(booking, booking_start, booking_end, start):
            # The new booking can join the booking's interval when it starts at start.
            return bool(
                way
                and booking.status == "scheduled"
                and start > now
                and (booking_start, booking_end) == (start, start + length)
                and booking.method_id == way.method_id
                and (
                    booking.machine_id == machine
                    if machine
                    else not booking.machine_id
                    and booking.person_id == person
                    and booking.sample_test_id.parameter_method_id == way
                )
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
                overlapping = [span for span in spans if span[1] < end and span[2] > start]
                joined = busy.browse([span[0].id for span in overlapping if shares(*span, start)])
                blocking = [span for span in overlapping if span[0] not in joined]
                if joined and len(joined.sample_test_id.sample_id | sample) > capacity:
                    blocking = overlapping
                if blocking:
                    # Try next where a later interval can be joined or where a blocking booking ends.
                    start = _round_up(
                        min(
                            span_start
                            if span_start > start and shares(booking, span_start, span_end, span_start)
                            else span_end
                            for booking, span_start, span_end in blocking
                        )
                    )
                    continue
                # Bookings sharing an interval book its rooms once.
                clash = _room_clash(
                    start, rooms, [event for event in room_busy if event.machine_booking_id not in joined]
                )
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
                ["location_id", "start", "stop", "machine_booking_id"],
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
