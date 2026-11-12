from datetime import timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .schedule_invariants_case import ScheduleInvariantsCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_MACHINE_BOOKING,
    MODEL_OVERTIME,
    MODEL_TESTING_METHOD_STEP,
)

SLOT = timedelta(minutes=15)
# Monday 18:00 UTC, after the testers' working hours.
EVENING = MONDAY.replace(hour=18)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOverTime(ScheduleInvariantsCase):
    """The head of the testers' department records OverTime; a tester of another department works in microbiology."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grant(
            cls.head,
            "overtime.read.own_department",
            "overtime.create.own_department",
            "overtime.edit.own_department",
            "overtime.delete.own_department",
        )
        cls.slow.status = "under_repair"

    def record(self, person=None, starts_at=EVENING, hours=3):
        """OverTime the head records for the person, the tester by default."""
        return self.as_person(self.env[MODEL_OVERTIME], self.head).create(
            {
                "person_id": (person or self.tester).id,
                "starts_at": starts_at,
                "ends_at": starts_at + timedelta(hours=hours),
                "reason": "Urgent lead tests would otherwise miss their due date.",
            }
        )

    def booked(self, test=None, person=None):
        """The booking of a test of the person, the tester by default, in their first free slot on the fast machine."""
        person = person or self.tester
        test = test or self.test
        self.testing_task(test, person)
        return self.schedule(test, person)

    def move(self, booking, start):
        booking.with_user(booking.person_id.user_id).write({"starts_at": start})

    def assert_refused(self, booking, start):
        with self.assertRaisesRegex(UserError, "is not free"):
            self.move(booking, start)
        self.assertEqual(booking.starts_at, MONDAY)

    def test_a_tester_is_booked_outside_hours_only_inside_their_overtime(self):
        booking = self.booked()
        self.assert_refused(booking, EVENING)

        overtime = self.record()
        self.assertEqual(overtime.create_uid, self.head.user_id)
        self.assertEqual(overtime.department_id, self.department)
        self.move(booking, EVENING)
        self.assertEqual((booking.starts_at, booking.ends_at), (EVENING, EVENING + 3 * SLOT))

        # The 40-minute run must end by the end of the OverTime at 21:00.
        with self.assertRaisesRegex(UserError, "is not free"):
            self.move(booking, EVENING + timedelta(hours=2, minutes=30))
        self.move(booking, EVENING + timedelta(hours=2, minutes=15))
        self.assertEqual(booking.ends_at, EVENING + timedelta(hours=3))

        # The OverTime is the tester's own: another tester stays within normal hours.
        other = self.booked(self.new_test(), self.other_tester)
        self.assert_refused(other, EVENING)

    def test_overtime_that_continues_the_working_day_takes_a_run_across_the_end_of_the_day(self):
        booking = self.booked()
        day_end = self.env[MODEL_MACHINE_BOOKING]._working_time(self.tester, MONDAY, MONDAY + timedelta(days=1))[-1][1]
        late = day_end - SLOT
        self.assert_refused(booking, late)
        self.record(starts_at=day_end, hours=1)
        self.move(booking, late)
        self.assertEqual((booking.starts_at, booking.ends_at), (late, late + 3 * SLOT))

    @freeze_time(MONDAY.replace(hour=17))
    def test_the_scheduler_books_a_test_due_tonight_in_the_overtime(self):
        test = self.new_test(EVENING + timedelta(hours=3))
        self.testing_task(test, self.tester)
        with self.assertRaisesRegex(UserError, "No machine can finish"), self.rolled_back():
            self.schedule(test, self.tester)
        self.record()
        booking = self.schedule(test, self.tester)
        self.assertEqual((booking.status, booking.starts_at), ("scheduled", EVENING))

    def test_moving_or_cancelling_a_booking_never_changes_overtime(self):
        overtime = self.record()
        fields = ["person_id", "department_id", "starts_at", "ends_at", "reason"]
        before = overtime.read(fields)
        booking = self.booked()
        self.move(booking, EVENING)
        self.move(booking, MONDAY + timedelta(hours=1))
        self.move(booking, EVENING + SLOT)
        booking.with_user(self.tester.user_id).action_cancel()
        self.env.invalidate_all()
        self.assertTrue(overtime.exists())
        self.assertEqual(overtime.read(fields), before)
        self.assertEqual(self.env[MODEL_OVERTIME].search_count([("person_id", "=", self.tester.id)]), 1)

    def test_overtime_does_not_make_a_machine_or_a_location_available(self):
        self.record()
        booking = self.booked()
        self.occupy(self.fast, EVENING, EVENING + timedelta(hours=1))
        self.assert_refused(booking, EVENING)

        room = self.env[MODEL_LOCATION].create({"code": "OT-PREP", "name": "OverTime preparation", "is_bookable": True})
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": self.method.id,
                "sequence": 1,
                "duration_minutes": 15,
                "instruction": "Weigh the test portion.",
                "location_id": room.id,
            }
        )
        later = EVENING + timedelta(hours=1)
        self.env[MODEL_CALENDAR_EVENT].create(
            {"name": "Method validation meeting", "start": later, "stop": later + SLOT, "location_id": room.id}
        )
        self.assert_refused(booking, later)
        self.move(booking, later + SLOT)
        self.assertEqual(booking.starts_at, later + SLOT)

    def test_overtime_ends_after_it_starts_and_does_not_overlap_for_the_same_tester(self):
        for hours in (0, -1):
            with self.subTest(hours=hours), self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
                with self.env.cr.savepoint():
                    self.record(hours=hours)
                    self.env.flush_all()
        self.record()
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.record(starts_at=EVENING + timedelta(hours=2))
            self.env.flush_all()
        # OverTime may start when the last one ends, and another tester's may overlap it.
        self.record(starts_at=EVENING + timedelta(hours=3))
        self.record(self.other_tester)
        self.env.flush_all()
        self.assertEqual(self.env[MODEL_OVERTIME].search_count([("person_id", "=", self.tester.id)]), 2)

    def test_the_head_records_overtime_only_for_their_own_department(self):
        overtime = self.record()
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            self.record(self.microbiologist)
        others = self.env[MODEL_OVERTIME].create(
            {
                "person_id": self.microbiologist.id,
                "starts_at": EVENING,
                "ends_at": EVENING + timedelta(hours=1),
                "reason": "Microbiology culture reading.",
            }
        )
        self.assertEqual(self.as_person(self.env[MODEL_OVERTIME], self.head).search([]), overtime)
        with self.assertRaises(AccessError):
            self.as_person(others, self.head).write({"reason": "Moved by another head."})
        with self.assertRaises(AccessError):
            self.as_person(self.env[MODEL_OVERTIME], self.tester).create(
                {"person_id": self.tester.id, "starts_at": EVENING, "ends_at": EVENING + SLOT, "reason": "Self."}
            )
