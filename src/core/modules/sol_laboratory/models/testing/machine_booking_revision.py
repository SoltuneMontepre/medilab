from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_PLAN_REVISION
from odoo.addons.sol_laboratory.models.testing.machine_booking import HORIZON_DAYS, _rooms_end

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingRevisionBase
else:
    MachineBookingRevisionBase = object


def _misses(booking, slot):
    """True when the booking has no slot, or its slot ends after its sample test's internal due date."""
    due_date = booking.sample_test_id.due_date
    return not slot or bool(due_date and slot[2] + slot[3] > due_date)


# Lịch Đặt Máy: urgent work takes the slots of scheduled bookings only through a plan revision the heads approve.
class MachineBookingRevision(models.Model, MachineBookingRevisionBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.model
    def _revise(self, department):
        """Propose the department's plan revision, or drop it when nothing needs one.

        Urgent work that waits as a proposed booking may need the slot of a scheduled booking that has not started. The
        recalculation then places the urgent bookings and the scheduled ones that may move, one at a time in priority
        order, each scheduled booking staying in its slot while that is free. A pinned booking never moves: the
        recalculation without it reports a conflict where it would. A move that would finish after its sample test's
        internal due date is held back, and the recalculation starts again with that booking where it is.
        """
        bookings = self.sudo()
        urgent = bookings.search(
            [("status", "=", "proposed"), ("department_id", "=", department.id)], order="id"
        ).filtered(lambda booking: booking.sample_test_id.priority == "urgent" and not booking.is_pinned)
        movable = bookings.search(
            [
                ("status", "=", "scheduled"),
                ("department_id", "=", department.id),
                ("starts_at", ">", fields.Datetime.now()),
            ],
            order="id",
        )
        rows, reason = [], ""
        if urgent and movable:
            rows, slots = bookings._revision_rows(department, urgent, movable)
            reason = bookings._revision_reason(slots)
        self.env[MODEL_PLAN_REVISION]._renew(department, rows, reason)

    @api.model
    def _revision_rows(self, department, urgent, movable):
        """What the revision holds, as (booking, slot, status) rows, and the slots found for the urgent bookings. A slot
        is (way, machine, start, length)."""
        pinned = movable.filtered("is_pinned")
        moved, held, slots = self._revision_slots(department, urgent, movable, pinned)
        rows = [(booking, slot, "proposed") for booking, slot in moved.items()]
        rows += [(booking, slot, "held_back") for booking, slot in held.items()]
        if pinned and any(_misses(booking, slot) for booking, slot in slots.items()):
            # Urgent work that still misses its due date shows where pinned bookings stand in the way: the moves the plan
            # would make if they could move.
            would_move, would_hold, _slots = self._revision_slots(department, urgent, movable, movable.browse())
            rows += [
                (booking, slot, "conflict")
                for booking, slot in {**would_move, **would_hold}.items()
                if booking.is_pinned
            ]
        return rows, slots

    @api.model
    def _revision_slots(self, department, urgent, movable, fixed):
        """Place the urgent bookings and the movable scheduled ones around the fixed ones, as (moved, held, urgent slots)
        dictionaries from booking to slot. Starts again with a booking whose move would pass its due date, or that no
        slot fits, fixed where it is; the held ones keep the slot they would have moved to."""
        held = {}
        while True:
            free = movable - fixed
            slots = self._place_by_priority(department, urgent, free)
            stuck = {booking: slot for booking, slot in slots.items() if booking in free and _misses(booking, slot)}
            if not stuck:
                break
            fixed |= self.browse().union(stuck)
            held.update({booking: slot for booking, slot in stuck.items() if slot})
        moved = {booking: slot for booking, slot in slots.items() if booking in free}
        return moved, held, {booking: slot for booking, slot in slots.items() if booking in urgent}

    @api.model
    def _place_by_priority(self, department, urgent, free):
        """Place the urgent bookings and the free scheduled ones one at a time in priority order, as the plan does. A
        scheduled booking stays in its slot while that is free, and otherwise takes the earliest slot of its method.
        Returns the slot of every booking that is not where it was, None for one no slot fits; nothing is written."""
        horizon = fields.Datetime.now() + timedelta(days=HORIZON_DAYS)
        planned = self.browse()
        slots = {}
        for booking in sorted(urgent | free, key=lambda booking: booking.sample_test_id._plan_key(department)):
            scheduled = booking.status == "scheduled"
            if scheduled and booking._stays(free, planned):
                planned |= self.new(
                    booking._simulation_values(
                        booking.machine_id, booking.method_id, booking.starts_at, booking.ends_at
                    )
                )
                continue
            slot = self._recommend(
                booking.sample_test_id,
                booking.person_id,
                department,
                planned=planned,
                due_date=horizon,
                ignore=free,
                method=booking.method_id if scheduled else None,
            )
            if slot:
                way, machine, start, length = slot
                planned |= self.new(booking._simulation_values(machine, way.method_id, start, start + length))
                if scheduled and (machine, start) == (booking.machine_id, booking.starts_at):
                    continue
            slots[booking] = slot
        return slots

    def _stays(self, ignore, planned):
        """True when the scheduled booking can stay in its slot with the ignored bookings out of the way and the planned
        ones in place."""
        self.ensure_one()
        test = self.sample_test_id
        way = test.parameter_method_id
        rooms = self._room_steps(way)
        start, end = self.starts_at, self.ends_at
        if not start or not end:
            return False
        length = end - start
        return start == self._free_slot(
            self.machine_id,
            length,
            self.person_id,
            start + max(length, _rooms_end(rooms)),
            start,
            ignore,
            rooms=rooms,
            way=way,
            sample=test.sample_id,
            planned=planned,
        )

    def _simulation_values(self, machine, method, start, end):
        """The values of an unsaved proposed booking that holds the slot while a simulation places other bookings."""
        self.ensure_one()
        return {
            "sample_test_id": self.sample_test_id.id,
            "task_id": self.task_id.id,
            "person_id": self.person_id.id,
            "machine_id": machine.id,
            "method_id": method.id,
            "starts_at": start,
            "ends_at": end,
            "status": "proposed",
        }

    @api.model
    def _revision_reason(self, slots):
        """Why the plan was recalculated: the urgent work it makes room for, and where each test would be measured."""
        zone = self.env.company.tz or "UTC"
        lines = []
        for booking, slot in slots.items():
            if not slot:
                lines.append(
                    self.env._(
                        "%(test)s has no slot within %(days)s days", test=booking.display_name, days=HORIZON_DAYS
                    )
                )
                continue
            start, end = slot[2], slot[2] + slot[3]
            due_date = booking.sample_test_id.due_date
            lines.append(
                self.env._(
                    "%(test)s from %(start)s, after its internal due date",
                    test=booking.display_name,
                    start=format_datetime(self.env, start, tz=zone),
                )
                if due_date and end > due_date
                else self.env._(
                    "%(test)s from %(start)s",
                    test=booking.display_name,
                    start=format_datetime(self.env, start, tz=zone),
                )
            )
        return self.env._("Makes room for urgent work: %s", "; ".join(lines))
