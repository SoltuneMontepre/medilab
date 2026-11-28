from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase, calibrated
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE, MODEL_MACHINE_BOOKING

LATER = MONDAY + timedelta(hours=2)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestBookingProposal(SchedulingCase):
    """The tester puts the booking the plan proposes for their task in a slot and on a machine of their choice, which
    the head of department approves."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department.manager_id = cls.head.employee_id

    def propose(self, test=None, tester=None):
        """The booking the plan proposes for the test once it is assigned to the tester."""
        test = test or self.test
        self.testing_task(test, tester or self.tester)
        return test.booking_ids

    def test_the_plan_keeps_the_testers_slot_and_machine_until_the_head_approves_it(self):
        booking = self.propose()
        self.assertEqual((booking.machine_id, booking.starts_at), (self.fast, MONDAY))

        booking.with_user(self.tester.user_id).write({"starts_at": LATER, "machine_id": self.slow.id})

        self.assertEqual(
            (booking.status, booking.machine_id, booking.starts_at, booking.ends_at, booking.is_pinned),
            ("proposed", self.slow, LATER, LATER + timedelta(minutes=75), True),
        )
        self.env[MODEL_MACHINE_BOOKING]._plan(self.department)
        self.assertEqual((booking.machine_id, booking.starts_at), (self.slow, LATER))

        booking.with_user(self.head.user_id).action_approve()

        self.assertEqual((booking.status, booking.starts_at, booking.is_pinned), ("scheduled", LATER, False))
        self.assertEqual(booking.calendar_event_id.user_id, self.tester.user_id)

    def test_the_plan_places_other_tests_around_the_testers_slot(self):
        booking = self.propose()
        booking.with_user(self.tester.user_id).write({"starts_at": MONDAY + timedelta(minutes=15)})

        other = self.propose(self.new_test(), self.other_tester)

        # The fast machine is taken from a quarter past, so the slow one finishes the other test first.
        self.assertEqual((booking.starts_at, booking.is_pinned), (MONDAY + timedelta(minutes=15), True))
        self.assertEqual((other.machine_id, other.starts_at), (self.slow, MONDAY))

    def test_a_slot_that_is_taken_or_a_machine_not_linked_to_the_method_is_refused(self):
        scheduled = self.propose(self.new_test(), self.other_tester)
        self.schedule(scheduled.sample_test_id, self.other_tester)
        booking = self.propose()
        unlinked = self.env[MODEL_MACHINE].create(calibrated({"code": "AAS-3", "name": "AAS 3"}))

        with self.assertRaisesRegex(UserError, "AAS 1 is not free for"):
            booking.with_user(self.tester.user_id).write({"starts_at": MONDAY, "machine_id": self.fast.id})
        with self.assertRaisesRegex(UserError, "is not linked to the testing method"):
            booking.with_user(self.tester.user_id).write({"starts_at": LATER, "machine_id": unlinked.id})

        self.assertFalse(booking.is_pinned)

    def test_only_the_tester_of_the_booking_or_the_head_proposes_its_slot(self):
        booking = self.propose()

        with self.assertRaises(AccessError):
            booking.with_user(self.other_tester.user_id).write({"starts_at": LATER})

        self.assertEqual((booking.starts_at, booking.is_pinned), (MONDAY, False))

    def test_the_head_returns_the_testers_slot_to_the_plan(self):
        booking = self.propose()
        booking.with_user(self.tester.user_id).write({"starts_at": LATER, "machine_id": self.slow.id})

        booking.with_user(self.head.user_id).action_return_to_plan()

        self.assertEqual((booking.machine_id, booking.starts_at, booking.is_pinned), (self.fast, MONDAY, False))

    def test_another_tester_of_the_task_gets_the_plans_slot(self):
        booking = self.propose()
        booking.with_user(self.tester.user_id).write({"starts_at": LATER, "machine_id": self.slow.id})

        self.test._latest_testing_task().write(
            {"assignee_id": self.other_tester.id, "reassign_reason": "Away this week"}
        )

        self.assertEqual(
            (booking.person_id, booking.machine_id, booking.starts_at, booking.is_pinned),
            (self.other_tester, self.fast, MONDAY, False),
        )
