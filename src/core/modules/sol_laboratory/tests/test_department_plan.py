from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.jobs import AT_RISK_SUMMARY_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_SAMPLE_TEST_AT_RISK

SLOT = timedelta(minutes=15)
RUN = 3 * SLOT


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestDepartmentPlan(SchedulingCase):
    """One AAS machine runs lead in 40 minutes, so the plan places its tests one after another."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"
        cls.department.manager_id = cls.head.employee_id

    def propose(self, test, person=None):
        """The booking the department's plan proposes for the test once it is assigned."""
        self.testing_task(test, person or self.tester)
        return test.booking_ids

    def slots(self, *bookings):
        return [booking.starts_at for booking in bookings]

    def test_urgent_tests_go_before_due_soon_ones_which_go_before_normal_ones(self):
        normal = self.propose(self.new_test())
        due_soon = self.propose(self.new_test(MONDAY + timedelta(hours=20)), self.other_tester)
        urgent_test = self.new_test()
        urgent = self.propose(urgent_test)

        urgent_test.with_user(self.tester.user_id)._mark_urgent("The customer needs it to clear customs")

        self.assertEqual((urgent_test.priority, due_soon.priority, normal.priority), ("urgent", "due_soon", "normal"))
        self.assertEqual(self.slots(urgent, due_soon, normal), [MONDAY, MONDAY + RUN, MONDAY + 2 * RUN])
        self.assertEqual(urgent_test.urgent_reason, "The customer needs it to clear customs")
        self.assertEqual(urgent_test.marked_urgent_by_id, self.tester)

    def test_within_a_class_the_earlier_committed_date_then_the_earlier_arrival_goes_first(self):
        later_date, second, first = self.new_test(), self.new_test(), self.new_test()
        later_date.sample_id.request_id.expected_date = "2026-10-25"
        bookings = [
            self.propose(test, person) for test, person in ((later_date, self.tester), (second, self.other_tester))
        ]
        bookings.append(self.propose(first))
        self.env[MODEL_SAMPLE_HANDOVER].search(
            [("sample_id", "=", first.sample_id.id), ("department_id", "=", self.department.id)]
        ).received_at = MONDAY - timedelta(hours=1)

        self.assertEqual(self.slots(*bookings), [MONDAY + 2 * RUN, MONDAY + RUN, MONDAY])

    def test_the_same_inputs_always_give_the_same_plan(self):
        bookings = self.propose(self.new_test()) | self.propose(self.new_test(), self.other_tester)
        before = [(booking.id, booking.machine_id, booking.starts_at, booking.ends_at) for booking in bookings]

        with patch.object(type(bookings), "_set") as written:
            self.env[MODEL_MACHINE_BOOKING]._plan(self.department)

        written.assert_not_called()
        after = [(booking.id, booking.machine_id, booking.starts_at, booking.ends_at) for booking in bookings]
        self.assertEqual(after, before)

    def test_a_proposed_slot_reserves_nothing_until_it_is_accepted(self):
        booking = self.propose(self.test)
        task = self.test._testing_task()

        self.assertEqual((booking.status, booking.starts_at), ("proposed", MONDAY))
        self.assertFalse(booking.calendar_event_id)
        self.assertFalse(task.planned_start)
        free = self.env[MODEL_MACHINE_BOOKING]._free_slot(self.fast, RUN, self.other_tester, MONDAY + timedelta(days=1))
        self.assertEqual(free, MONDAY)

        booking.with_user(self.tester.user_id).action_accept()

        self.assertEqual(booking.status, "scheduled")
        self.assertEqual((booking.calendar_event_id.start, booking.calendar_event_id.stop), (MONDAY, MONDAY + RUN))
        self.assertEqual((task.planned_start, task.planned_end), (MONDAY, MONDAY + RUN))

    def test_accepting_a_slot_taken_meanwhile_reserves_nothing(self):
        booking = self.propose(self.test)
        other = self.propose(self.new_test(), self.other_tester)
        # Another acceptance takes the machine at the proposed time first.
        other._set({"starts_at": MONDAY, "ends_at": MONDAY + RUN, "status": "scheduled"})

        with self.assertRaisesRegex(UserError, "was taken meanwhile"):
            booking.with_user(self.tester.user_id).action_accept()

        self.assertEqual(booking.status, "proposed")
        self.assertFalse(booking.calendar_event_id)

    def test_the_plan_never_moves_a_scheduled_booking(self):
        self.testing_task(self.test, self.tester)
        scheduled = self.schedule(self.test, self.tester)
        urgent_test = self.new_test()
        urgent = self.propose(urgent_test, self.other_tester)

        urgent_test.with_user(self.head.user_id)._mark_urgent("Needed for a recall")

        self.assertEqual((scheduled.status, scheduled.starts_at), ("scheduled", MONDAY))
        self.assertEqual(urgent.starts_at, MONDAY + RUN)

    def test_marking_urgent_needs_a_reason_and_the_tester_of_the_task_or_its_head(self):
        self.propose(self.test)
        with self.assertRaisesRegex(UserError, "Give a reason"):
            self.test.with_user(self.tester.user_id)._mark_urgent(" ")
        with self.assertRaisesRegex(UserError, "Only the tester"):
            self.test.with_user(self.other_tester.user_id)._mark_urgent("Customer asked")

        self.test.with_user(self.head.user_id)._mark_urgent("Customer asked")
        self.assertEqual((self.test.priority, self.test.marked_urgent_by_id), ("urgent", self.head))

        self.test.with_user(self.tester.user_id).action_unmark_urgent()
        self.assertEqual((self.test.marked_urgent, self.test.urgent_reason), (False, False))

    def test_a_planned_finish_after_the_internal_due_date_flags_the_test_and_tells_its_tester_and_head(self):
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        self.assertFalse(self.test.at_risk)
        messages = self.env[MODEL_MAIL_MESSAGE]
        with patch.object(type(messages), "raise_event", autospec=True, side_effect=type(messages).raise_event) as told:
            self.test.write(
                {"due_date": MONDAY + timedelta(minutes=30), "due_date_reason": "The machine goes to service"}
            )

        self.assertGreater(booking.ends_at, self.test.due_date)
        self.assertTrue(self.test.at_risk)
        [call] = [call for call in told.call_args_list if call.args[1] == EVENT_SAMPLE_TEST_AT_RISK]
        self.assertEqual(call.kwargs["partners"], self.tester.user_id.partner_id | self.head.user_id.partner_id)

        self.test.write({"due_date": MONDAY + timedelta(days=2)})
        self.assertFalse(self.test.at_risk)

    def test_a_test_no_slot_lets_finish_in_time_is_at_risk(self):
        test = self.new_test(MONDAY + timedelta(minutes=30))
        booking = self.propose(test)

        self.assertEqual((booking.status, booking.starts_at), ("proposed", False))
        self.assertTrue(test.at_risk)
        self.assertTrue(test.outsourcing_suggested)

    def test_flagging_a_test_at_risk_tells_its_tester_and_head_once(self):
        self.propose(self.test)
        messages = self.env[MODEL_MAIL_MESSAGE]
        with patch.object(type(messages), "raise_event", autospec=True) as told:
            self.test._flag_at_risk()
            self.test._flag_at_risk()

        self.assertTrue(self.test.at_risk)
        self.assertEqual(told.call_count, 1)

    def test_the_tester_and_head_get_a_daily_summary_of_the_tests_still_at_risk(self):
        test = self.new_test(MONDAY + timedelta(minutes=30))
        self.propose(test)
        self.assertTrue(test.at_risk)

        self.env[MODEL_SCHEDULED_JOB]._run_key(AT_RISK_SUMMARY_JOB)

        summaries = self.env[MODEL_MAIL_MESSAGE].search([("notification_key", "like", "at_risk_summary:%")])
        self.assertEqual(
            sorted(summaries.mapped("res_id")),
            sorted((self.tester.user_id.partner_id | self.head.user_id.partner_id).ids),
        )
        self.assertIn(test.sample_id.code, summaries[0].body)
