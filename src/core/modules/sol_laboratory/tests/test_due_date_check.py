from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .schedule_invariants_case import ScheduleInvariantsCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_RESOURCE_CALENDAR_LEAVES,
    MODEL_SAMPLE_TEST_DUE_DATE_CHANGE,
)

# An hour before the working day starts, so the bookings the plan places from 08:00 have not started.
NOW = MONDAY - timedelta(hours=1)
SLOT = timedelta(minutes=15)
RUN = 3 * SLOT
REASON = "The customer will collect the report on Monday."


@freeze_time(NOW)
@tagged("post_install", "-at_install")
class TestDueDateCheck(ScheduleInvariantsCase):
    """One AAS machine runs lead in 45 minutes. Its scheduled bookings and the tester's days decide which due dates the
    head of Analytical chemistry can set."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"
        cls.department.manager_id = cls.head.employee_id
        cls.env.company.tz = "UTC"

    def waiting(self):
        """The head's test, assigned to the tester, whose proposed booking reserves nothing."""
        self.testing_task(self.test, self.tester)
        return self.test

    def scheduled(self, due_date=None):
        """The booking of another test, scheduled on the machine from 08:00 for the other tester."""
        test = self.new_test(due_date)
        self.testing_task(test, self.other_tester)
        return self.schedule(test, self.other_tester)

    def wizard(self, person, due_date, reason=REASON):
        return (
            self.env[MODEL_SAMPLE_TEST_DUE_DATE_CHANGE]
            .with_user(person.user_id)
            .create({"sample_test_id": self.test.id, "due_date": due_date, "reason": reason})
        )

    def test_a_date_with_a_free_slot_is_feasible_and_checking_it_changes_nothing(self):
        booking = self.scheduled()
        self.waiting()
        before = self.graph(self.test | booking.sample_test_id)
        bookings = self.env[MODEL_MACHINE_BOOKING].search_count([])

        check = self.test._check_due_date(NOW + timedelta(hours=3))

        self.assertEqual((check.feasible, check.moves, check.reasons), (True, [], []))
        self.assertEqual(self.graph(self.test | booking.sample_test_id), before)
        self.assertEqual(self.env[MODEL_MACHINE_BOOKING].search_count([]), bookings)

    def test_a_date_no_free_slot_reaches_is_infeasible_with_reasons_and_the_earliest_date(self):
        self.waiting()
        monday_end = datetime(2026, 10, 12, 23, 59, 59)

        check = self.test._check_due_date(MONDAY + 2 * SLOT)

        self.assertFalse(check.feasible)
        self.assertEqual(len(check.reasons), 1)
        self.assertIn("after the due date", check.reasons[0])
        self.assertEqual(check.earliest, monday_end)
        passed = self.test._check_due_date(NOW - timedelta(hours=1))
        self.assertIn("has already passed", passed.reasons[0])
        self.assertEqual(passed.earliest, monday_end)
        # Without a tester the plan still checks the machine and the company's working time.
        unassigned = self.new_test()
        self.testing_task(unassigned)
        self.assertFalse(unassigned._check_due_date(MONDAY + 2 * SLOT).feasible)
        self.assertTrue(unassigned._check_due_date(MONDAY + 4 * SLOT).feasible)

    def test_simulated_moves_make_room_when_each_moved_booking_keeps_its_due_date(self):
        booking = self.scheduled(NOW + timedelta(days=5))
        self.waiting()
        before = self.graph(self.test | booking.sample_test_id)

        check = self.test._check_due_date(MONDAY + 4 * SLOT)

        self.assertTrue(check.feasible)
        # The machine is free from 08:45, which is too late; the booking on it moves behind this test.
        self.assertEqual(check.moves, [(booking, MONDAY + RUN, MONDAY + 2 * RUN)])
        self.assertEqual(self.graph(self.test | booking.sample_test_id), before)
        self.assertEqual((booking.status, booking.starts_at), ("scheduled", MONDAY))
        self.assert_schedule_invariants(self.test | booking.sample_test_id)

    def test_moves_that_would_pass_another_due_date_leave_the_date_infeasible(self):
        booking = self.scheduled(MONDAY + 4 * SLOT)
        self.waiting()

        check = self.test._check_due_date(MONDAY + 4 * SLOT)

        self.assertFalse(check.feasible)
        self.assertTrue(any(booking.display_name in reason for reason in check.reasons))
        self.assertEqual(check.earliest, datetime(2026, 10, 12, 23, 59, 59))
        self.assertEqual((booking.status, booking.starts_at), ("scheduled", MONDAY))

    def test_the_testers_leave_and_a_holiday_set_the_earliest_date_and_a_working_holiday_does_not(self):
        self.waiting()
        leaves = self.env[MODEL_RESOURCE_CALENDAR_LEAVES]
        leaves.create(
            {
                "name": "Annual leave",
                "resource_id": self.tester.resource_id.id,
                "date_from": MONDAY - timedelta(hours=8),
                "date_to": MONDAY + timedelta(hours=16),
            }
        )
        due_date = MONDAY + timedelta(hours=8)

        check = self.test._check_due_date(due_date)

        self.assertFalse(check.feasible)
        self.assertTrue(any(self.tester.display_name in reason for reason in check.reasons))
        self.assertEqual(check.earliest, datetime(2026, 10, 13, 23, 59, 59))

        holiday = leaves.create(
            {
                "name": "Public holiday",
                "date_from": datetime(2026, 10, 13, 0, 0, 0),
                "date_to": datetime(2026, 10, 13, 23, 59, 59),
            }
        )
        self.assertEqual(self.test._check_due_date(due_date).earliest, datetime(2026, 10, 14, 23, 59, 59))
        holiday.count_as = "working_time"
        self.assertEqual(self.test._check_due_date(due_date).earliest, datetime(2026, 10, 13, 23, 59, 59))

    def test_a_measurement_in_progress_is_not_moved(self):
        booking = self.schedule(self.waiting(), self.tester)
        booking.with_user(self.tester.user_id).action_start()

        self.assertTrue(self.test._check_due_date(MONDAY + 4 * SLOT).feasible)
        check = self.test._check_due_date(MONDAY + 2 * SLOT)

        self.assertFalse(check.feasible)
        self.assertIn("measurement in progress", check.reasons[0])

    def test_an_outsourced_test_needs_no_resource_of_the_laboratory(self):
        self.test.status = "outsourced"

        self.assertTrue(self.test._check_due_date(NOW + timedelta(minutes=5)).feasible)

    def test_the_head_keeps_an_infeasible_date_with_a_reason_and_the_test_is_at_risk(self):
        self.waiting()
        infeasible = MONDAY + 2 * SLOT

        change = self.wizard(self.head, infeasible)
        self.assertEqual(change.feasibility, "infeasible")
        self.assertEqual(change.earliest_feasible_date, datetime(2026, 10, 12, 23, 59, 59))
        self.assertIn("after the due date", change.check_message or "")
        with self.assertRaisesRegex(UserError, "cannot meet this due date"):
            change.action_change()
        self.assertNotEqual(self.test.due_date, infeasible)
        with self.assertRaises(UserError):
            self.wizard(self.head, infeasible, " ").action_keep_at_risk()

        change.action_keep_at_risk()

        self.assertEqual((self.test.due_date, self.test.due_date_reason), (infeasible, REASON))
        self.assertTrue(self.test.at_risk)

    def test_only_the_head_checks_a_date_and_keeps_it_at_risk(self):
        self.waiting()
        infeasible = MONDAY + 2 * SLOT

        change = self.wizard(self.tester, infeasible)

        self.assertFalse(change.feasibility)
        with self.assertRaises(UserError):
            change.action_keep_at_risk()
        self.assertNotEqual(self.test.due_date, infeasible)

    def test_the_head_accepts_a_date_made_feasible_by_simulated_moves_and_nothing_moves(self):
        booking = self.scheduled(NOW + timedelta(days=5))
        self.waiting()
        due_date = MONDAY + 4 * SLOT
        before = self.graph(booking.sample_test_id)

        change = self.wizard(self.head, due_date)
        self.assertEqual(change.feasibility, "moves")
        self.assertIn(booking.display_name, change.check_message or "")
        change.action_change()

        self.assertEqual((self.test.due_date, self.test.due_date_reason), (due_date, REASON))
        self.assertEqual(self.graph(booking.sample_test_id), before)
        self.assertEqual(self.wizard(self.head, NOW + timedelta(hours=3)).feasibility, "free")
