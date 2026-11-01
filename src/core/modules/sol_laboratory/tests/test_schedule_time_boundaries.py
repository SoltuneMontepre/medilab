from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .lab_timezone_case import LabTimezoneCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE, MODEL_MACHINE_BOOKING

SLOT = timedelta(minutes=15)
# The end of Monday 2026-10-12 in Vietnam, in UTC.
VIETNAM_MIDNIGHT = datetime(2026, 10, 12, 17, 0)
DUE_MONDAY_IN_VIETNAM = datetime(2026, 10, 12, 16, 59, 59)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleTimeBoundaries(LabTimezoneCase):
    def working_time(self, start, end):
        return self.env[MODEL_MACHINE_BOOKING]._working_time(self.tester, start, end)

    def recommendation(self, test):
        test.invalidate_recordset()
        return test.recommended_machine_id, test.recommended_start, test.recommended_end

    def assert_no_slot(self, test):
        self.assertEqual(self.recommendation(test), (self.env[MODEL_MACHINE], False, False))
        self.assertTrue(test.outsourcing_suggested)
        with self.assertRaisesRegex(UserError, "No machine can finish"), self.rolled_back():
            self.schedule(test, self.tester)
        self.assertFalse(test.booking_ids)

    def test_a_run_may_end_at_its_due_date(self):
        self.slow.status = "under_repair"
        test = self.new_test(MONDAY + 3 * SLOT)
        self.testing_task(test, self.tester)
        self.assertEqual(self.recommendation(test), (self.fast, MONDAY, MONDAY + 3 * SLOT))
        booking = self.schedule(test, self.tester)
        self.assertEqual((booking.status, booking.starts_at, booking.ends_at), ("scheduled", MONDAY, test.due_date))
        self.assert_schedule_invariants(test)

    def test_a_run_ending_a_second_after_its_due_date_gets_no_slot(self):
        self.slow.status = "under_repair"
        test = self.new_test(MONDAY + 3 * SLOT - timedelta(seconds=1))
        self.testing_task(test, self.tester)
        self.assert_no_slot(test)
        self.assert_schedule_invariants(test)

    def test_a_test_due_now_or_already_due_gets_no_slot(self):
        for due in (MONDAY, MONDAY - timedelta(seconds=1)):
            with self.subTest(due=due), self.rolled_back():
                test = self.new_test(due)
                self.testing_task(test, self.tester)
                self.assertFalse(self.env[MODEL_MACHINE_BOOKING]._recommend(test, self.tester, self.department))
                self.assert_no_slot(test)
                self.assert_schedule_invariants(test)

    @freeze_time("2026-10-12 00:30:00")
    def test_working_hours_in_vietnam_are_placed_in_utc(self):
        self.in_vietnam(self.tester, self.office_hours)
        monday = datetime(2026, 10, 12)
        self.assertEqual(
            self.working_time(monday, monday + timedelta(days=1)),
            [(monday.replace(hour=1), monday.replace(hour=5)), (monday.replace(hour=6), monday.replace(hour=10))],
        )
        self.slow.status = "under_repair"
        self.testing_task(self.test, self.tester)
        self.assertEqual(
            self.recommendation(self.test), (self.fast, monday.replace(hour=1), datetime(2026, 10, 12, 1, 45))
        )
        with self.rolled_back():
            self.occupy(self.fast, monday.replace(hour=1), monday.replace(hour=5))
            self.assertEqual(
                self.recommendation(self.test), (self.fast, monday.replace(hour=6), datetime(2026, 10, 12, 6, 45))
            )
        booking = self.schedule(self.test, self.tester)
        self.assertEqual((booking.starts_at, booking.ends_at), (monday.replace(hour=1), datetime(2026, 10, 12, 1, 45)))
        self.assert_schedule_invariants(self.test)

    @freeze_time("2026-10-12 00:30:00")
    def test_the_end_of_office_hours_in_vietnam_ends_the_last_slot_of_the_day(self):
        self.in_vietnam(self.tester, self.office_hours)
        self.slow.status = "under_repair"
        test = self.lead_test_expected_on("2026-10-14")
        self.assertEqual(test.due_date, DUE_MONDAY_IN_VIETNAM)
        start = datetime(2026, 10, 12, 1, 0)
        with self.subTest(busy_until="09:15"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 9, 15))
            self.testing_task(test, self.tester)
            self.assertEqual(
                self.recommendation(test), (self.fast, datetime(2026, 10, 12, 9, 15), datetime(2026, 10, 12, 10, 0))
            )
            booking = self.schedule(test, self.tester)
            self.assertEqual(booking.ends_at, datetime(2026, 10, 12, 10, 0))
            self.assert_schedule_invariants(test)
        with self.subTest(busy_until="09:30"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 9, 30))
            self.testing_task(test, self.tester)
            self.assert_no_slot(test)
            self.assert_schedule_invariants(test)

    @freeze_time("2026-10-12 15:00:00")
    def test_a_due_date_at_the_end_of_the_day_in_vietnam_ends_the_last_slot(self):
        self.in_vietnam(self.tester, self.utc_evening, tz="UTC")
        self.slow.status = "under_repair"
        test = self.lead_test_expected_on("2026-10-14")
        self.assertEqual(test.due_date, DUE_MONDAY_IN_VIETNAM)
        start = datetime(2026, 10, 12, 15, 0)
        self.assertEqual(self.working_time(start, start + timedelta(hours=4)), [(start, start + timedelta(hours=4))])
        with self.subTest(busy_until="16:00"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 16, 0))
            self.testing_task(test, self.tester)
            booking = self.schedule(test, self.tester)
            self.assertEqual(
                (booking.starts_at, booking.ends_at), (datetime(2026, 10, 12, 16, 0), datetime(2026, 10, 12, 16, 45))
            )
            self.assert_schedule_invariants(test)
        with self.subTest(busy_until="16:15"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 16, 15))
            self.testing_task(test, self.tester)
            # The machine and the person are free until 19:00: one second more of due date would fit the slot.
            free = self.env[MODEL_MACHINE_BOOKING]._free_slot(self.fast, 3 * SLOT, self.tester, VIETNAM_MIDNIGHT)
            self.assertEqual(free, datetime(2026, 10, 12, 16, 15))
            self.assert_no_slot(test)
            self.assert_schedule_invariants(test)

    @freeze_time("2026-10-12 15:00:00")
    def test_a_machine_is_bookable_until_the_end_of_its_calibration_date_in_vietnam(self):
        self.in_vietnam(self.tester, self.utc_evening, tz="UTC")
        self.slow.status = "under_repair"
        self.fast.service_ids = [
            Command.create({"kind": "calibration", "service_date": "2025-10-12", "next_due_date": "2026-10-12"})
        ]
        self.assertEqual(self.fast._usable_until(), VIETNAM_MIDNIGHT)
        start = datetime(2026, 10, 12, 15, 0)
        with self.subTest(busy_until="16:15"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 16, 15))
            self.testing_task(self.test, self.tester)
            booking = self.schedule(self.test, self.tester)
            self.assertEqual((booking.starts_at, booking.ends_at), (datetime(2026, 10, 12, 16, 15), VIETNAM_MIDNIGHT))
            self.fast.service_ids.write({"next_due_date": "2026-10-12"})
            self.assertEqual(
                (booking.status, booking.machine_id, booking.starts_at, booking.ends_at),
                ("scheduled", self.fast, datetime(2026, 10, 12, 16, 15), VIETNAM_MIDNIGHT),
            )
            self.assert_schedule_invariants(self.test)
        with self.subTest(busy_until="16:30"), self.rolled_back():
            self.occupy(self.fast, start, datetime(2026, 10, 12, 16, 30))
            self.testing_task(self.test, self.tester)
            self.assert_no_slot(self.test)
            self.fast.service_ids.write({"next_due_date": "2026-10-13"})
            self.assertEqual(
                self.recommendation(self.test),
                (self.fast, datetime(2026, 10, 12, 16, 30), datetime(2026, 10, 12, 17, 15)),
            )
            self.assert_schedule_invariants(self.test)
