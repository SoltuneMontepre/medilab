import re
from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .schedule_invariants_case import ScheduleInvariantsCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_TEST_RESULT

SLOT = timedelta(minutes=15)
MOVED_TO = MONDAY + timedelta(hours=6)
REFUSALS = {
    "start": "Only a scheduled booking can be started.",
    "done": "Only a booking in progress can be done.",
    "cancel": "Only a queued or scheduled booking can be cancelled.",
    "move": "Only a scheduled booking can be moved.",
}
ALLOWED = {
    ("queued", "cancel"),
    ("scheduled", "start"),
    ("scheduled", "cancel"),
    ("scheduled", "move"),
    ("in_progress", "done"),
}


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleStateMachine(ScheduleInvariantsCase):
    def statuses(self, test):
        self.env.invalidate_all()
        test = test.sudo()
        booking = test.booking_ids.filtered(lambda booking: booking.status != "cancelled")
        return test.status, test._testing_task().status, booking.status or None

    def test_a_received_sample_test_goes_from_its_queue_to_a_done_booking(self):
        self.grant(self.tester, "test_result.read.all", "test_result.create.all")
        staff = self.env.ref("sol_laboratory.person_administrator").user_id
        self.sample.with_user(staff).action_receive("2 bottles of 1 L", "good")
        self.assertEqual(self.statuses(self.test), ("waiting", "open", None))
        self.assert_schedule_invariants(self.test)

        task = self.test._testing_task()
        self.as_person(task, self.tester).action_claim()
        self.assertEqual(self.statuses(self.test), ("assigned", "assigned", None))
        self.assertEqual(task.assignee_id, self.tester)
        self.assert_schedule_invariants(self.test)

        booking = self.schedule(self.test, self.tester)
        self.assertEqual(self.statuses(self.test), ("assigned", "assigned", "scheduled"))
        self.assertEqual(
            (booking.machine_id, booking.starts_at, booking.ends_at), (self.fast, MONDAY, MONDAY + 3 * SLOT)
        )
        self.assert_schedule_invariants(self.test)

        booking.with_user(self.tester.user_id).action_start()
        test_status, _task_status, booking_status = self.statuses(self.test)
        self.assertEqual((test_status, booking_status), ("testing", "in_progress"))
        self.assert_schedule_invariants(self.test)

        event = booking.calendar_event_id
        self.env[MODEL_TEST_RESULT].with_user(self.tester.user_id).create(
            {"sample_test_id": self.test.id, "value": 0.008}
        )
        test_status, _task_status, booking_status = self.statuses(self.test)
        self.assertEqual((test_status, booking_status), ("testing", "done"))
        self.assertEqual(booking.calendar_event_id, event)
        self.assertEqual((event.start, event.stop), (MONDAY, MONDAY + 3 * SLOT))
        self.assert_schedule_invariants(self.test)

    def booking_in(self, status):
        """A booking of a new lead test for the tester, brought to the status by its own actions."""
        if status == "queued":
            # No machine can finish a 40-minute run within 30 minutes.
            test = self.new_test(MONDAY + 2 * SLOT)
            task = self.testing_task(test, self.tester)
            booking = self.env[MODEL_MACHINE_BOOKING].create(
                {
                    "machine_id": self.fast.id,
                    "sample_test_id": test.id,
                    "task_id": task.id,
                    "person_id": self.tester.id,
                }
            )
            self.env[MODEL_MACHINE_BOOKING]._process_queue()
            self.assertEqual(booking.status, "queued")
            return booking
        test = self.new_test()
        self.testing_task(test, self.tester)
        booking = self.schedule(test, self.tester).with_user(self.tester.user_id)
        if status in ("in_progress", "done"):
            booking.action_start()
        if status == "done":
            booking.action_done()
        if status == "cancelled":
            booking.action_cancel()
        self.assertEqual(booking.status, status)
        return booking

    @staticmethod
    def act(booking, action):
        if action == "move":
            booking.write({"starts_at": MOVED_TO})
        else:
            getattr(booking, f"action_{action}")()

    def test_a_booking_takes_only_the_transitions_of_its_status(self):
        for status in ("queued", "scheduled", "in_progress", "done", "cancelled"):
            for action, refusal in REFUSALS.items():
                with self.subTest(status=status, action=action), self.rolled_back():
                    booking = self.booking_in(status)
                    test = booking.sample_test_id
                    if (status, action) in ALLOWED:
                        self.act(booking, action)
                        self.assert_allowed(booking, action)
                    else:
                        before = self.graph(test)
                        with self.assertRaisesRegex(UserError, re.escape(refusal)), self.rolled_back():
                            self.act(booking, action)
                        self.assertEqual(self.graph(test), before)
                    self.assert_schedule_invariants(test)

    def assert_allowed(self, booking, action):
        test = booking.sample_test_id.sudo()
        task = test._testing_task()
        if action == "cancel":
            self.assertEqual(booking.status, "cancelled")
            self.assertFalse(booking.calendar_event_id)
            self.assertEqual((task.planned_start, task.planned_end), (False, False))
            self.assertEqual(test.status, "assigned")
        elif action == "start":
            self.assertEqual((booking.status, test.status), ("in_progress", "testing"))
            self.assertTrue(booking.calendar_event_id)
        elif action == "move":
            self.assertEqual(booking.status, "scheduled")
            self.assertEqual((booking.starts_at, booking.ends_at), (MOVED_TO, MOVED_TO + 3 * SLOT))
            self.assertEqual((task.planned_start, task.planned_end), (MOVED_TO, MOVED_TO + 3 * SLOT))
        elif action == "done":
            self.assertEqual((booking.status, test.status), ("done", "testing"))
            self.assertEqual(
                (booking.calendar_event_id.start, booking.calendar_event_id.stop), (booking.starts_at, booking.ends_at)
            )
