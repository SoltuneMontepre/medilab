from contextlib import closing

from odoo.fields import Command
from odoo.tools import SQL

from .scheduling_case import SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CALENDAR_EVENT, MODEL_MACHINE_BOOKING, MODEL_TASK
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES, OPEN_STATUSES, SLOT_MINUTES

CLOSED_TEST_STATUSES = ("cancelled", "outsourced", "result_entered", "approved")
WEEKDAYS = range(5)


class ScheduleInvariantsCase(SchedulingCase):
    """Scheduling fixtures whose bookings are checked, from the database, against the rules every schedule keeps."""

    @classmethod
    def occupy(cls, machine, start, end):
        """A booking of another test that holds the machine from start to end."""
        blocker = cls.env[MODEL_MACHINE_BOOKING].create({"machine_id": machine.id, "sample_test_id": cls.new_test().id})
        blocker._set({"status": "scheduled", "starts_at": start, "ends_at": end})
        return blocker

    @classmethod
    def create_calendar(cls, name, attendances):
        """A working calendar of (weekday, from hour, to hour) attendances."""
        return cls.env["resource.calendar"].create(
            {
                "name": name,
                "attendance_ids": [
                    Command.create({"dayofweek": str(day), "hour_from": start, "hour_to": end})
                    for day, start, end in attendances
                ],
            }
        )

    def rolled_back(self):
        """A savepoint undone when the block ends, so each cell of a decision table starts from the same data."""
        return closing(self.env.cr.savepoint())

    def graph(self, tests):
        """The scheduling state of the tests: their bookings, testing tasks and calendar events."""
        self.env.flush_all()
        self.env.invalidate_all()
        tests = tests.sudo().sorted("id")
        bookings = tests.booking_ids.sorted("id")
        tasks = self.env[MODEL_TASK].union(test._testing_task() for test in tests)
        return {
            "bookings": bookings.read(
                ["status", "machine_id", "person_id", "starts_at", "ends_at", "calendar_event_id", "room_event_ids"]
            ),
            "tests": tests.read(["status", "parameter_method_id", "outsourcing_suggested"]),
            "tasks": tasks.read(["status", "assignee_id", "planned_start", "planned_end"]),
            "events": (bookings.calendar_event_id | bookings.room_event_ids)
            .sorted("id")
            .read(["start", "stop", "active", "user_id", "partner_ids", "location_id", "machine_booking_id"]),
        }

    def assert_schedule_invariants(self, tests):
        """P1 to P9 of the WF-03 test plan, for the bookings of the tests."""
        self.env.flush_all()
        self.env.invalidate_all()
        tests = tests.sudo()
        bookings = tests.booking_ids
        table = SQL.identifier(self.env[MODEL_MACHINE_BOOKING]._table)
        events_table = SQL.identifier(self.env[MODEL_CALENDAR_EVENT]._table)
        self.env.cr.execute(
            SQL(
                """SELECT a.id, b.id FROM %(table)s a JOIN %(table)s b ON b.machine_id = a.machine_id AND b.id <> a.id
                    WHERE a.id = ANY(%(ids)s) AND a.status IN %(active)s AND b.status IN %(active)s
                      AND tsrange(a.starts_at, a.ends_at) && tsrange(b.starts_at, b.ends_at)""",
                table=table,
                ids=bookings.ids,
                active=ACTIVE_STATUSES,
            )
        )
        self.assertFalse(self.env.cr.fetchall(), "P1: bookings of one machine overlap")
        self.env.cr.execute(
            SQL(
                """SELECT a.id, b.id FROM %(events)s a JOIN %(events)s b ON b.location_id = a.location_id AND b.id <> a.id
                    WHERE a.machine_booking_id = ANY(%(ids)s) AND a.active AND b.active
                      AND tsrange(a.start, a.stop) && tsrange(b.start, b.stop)""",
                events=events_table,
                ids=bookings.ids,
            )
        )
        self.assertFalse(self.env.cr.fetchall(), "P2: bookings of one room overlap")
        self.env.cr.execute(
            SQL(
                """SELECT sample_test_id FROM %(table)s WHERE sample_test_id = ANY(%(ids)s) AND status IN %(open)s
                    GROUP BY sample_test_id HAVING count(*) > 1""",
                table=table,
                ids=tests.ids,
                open=OPEN_STATUSES,
            )
        )
        self.assertFalse(self.env.cr.fetchall(), "P4: a test has more than one open booking")
        for booking in bookings:
            label = f"booking {booking.id} ({booking.status})"
            if booking.status in ACTIVE_STATUSES:
                self.assertTrue(booking.starts_at and booking.ends_at, f"P3: {label} has no slot")
                self.assertGreater(booking.ends_at, booking.starts_at, f"P3: {label} ends before it starts")
                start = booking.starts_at
                self.assertEqual(
                    (start.minute % SLOT_MINUTES, start.second, start.microsecond), (0, 0, 0), f"P3: {label}"
                )
            if booking.status in ("queued", "scheduled"):
                self.assertEqual(booking.person_id, booking.task_id.assignee_id, f"P5: {label} person")
            if booking.status == "scheduled":
                self.assertLessEqual(booking.ends_at, booking.machine_id._usable_until(), f"P9: {label}")
            self.assert_calendar_follows(booking, label)
        for test in tests:
            task = test._testing_task()
            if task and test.status in ("waiting", "assigned"):
                expected = "assigned" if task.assignee_id else "waiting"
                self.assertEqual(test.status, expected, f"P6: test {test.id} does not follow its task")
            if test.status in CLOSED_TEST_STATUSES:
                self.assertFalse(test.booking_ids._open(), f"P8: closed test {test.id} has an open booking")
        for task in bookings.task_id:
            slots = task.booking_ids.filtered(lambda booking: booking.status != "cancelled" and booking.starts_at)
            self.assertEqual(
                (task.planned_start, task.planned_end),
                (min(slots.mapped("starts_at"), default=False), max(slots.mapped("ends_at"), default=False)),
                f"P7: task {task.id} planned time",
            )

    def assert_calendar_follows(self, booking, label):
        """P7: an active booking is on its person's calendar and books its step rooms; a waiting or cancelled one is
        on no calendar; a done one keeps its events."""
        event = booking.calendar_event_id
        if booking.status == "done":
            return
        if booking.status not in ACTIVE_STATUSES:
            self.assertFalse(event, f"P7: {label} keeps a calendar event")
            self.assertFalse(booking.room_event_ids, f"P7: {label} keeps room bookings")
            return
        user = booking.person_id.user_id
        if not user:
            self.assertFalse(event, f"P7: {label} has an event without a user")
            return
        self.assertEqual((event.start, event.stop), (booking.starts_at, booking.ends_at), f"P7: {label} event")
        self.assertEqual(event.user_id, user, f"P7: {label} event owner")
        self.assertEqual(event.partner_ids, user.partner_id, f"P7: {label} attendees")
        self.assertFalse(event.alarm_ids, f"P7: {label} alarms")
        expected = {
            (step.id, step.location_id.id, booking.starts_at + offset, booking.starts_at + offset + length)
            for step, offset, length in booking._room_steps(booking.sample_test_id.parameter_method_id)
        }
        rooms = {(room.step_id.id, room.location_id.id, room.start, room.stop) for room in booking.room_event_ids}
        self.assertEqual(rooms, expected, f"P7: {label} room bookings")
