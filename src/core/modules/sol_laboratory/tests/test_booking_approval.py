from datetime import timedelta
from os import times
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .location_case import LocationCase
from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MAIL_MESSAGE,
    MODEL_TESTING_METHOD_STEP,
)

APPROVED_EVENT = "sol_laboratory.event_machine_booking_approved"
AT_RISK_EVENT = "sol_laboratory.event_sample_test_at_risk"
SLOT = timedelta(minutes=15)
RUN = 3 * SLOT


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestBookingApproval(SchedulingCase, LocationCase):
    """One AAS machine runs lead in 40 minutes after a weighing in a bookable room; the head of department approves
    what the plan proposes for the assigned tester."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"
        cls.department.manager_id = cls.head.employee_id
        cls.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": cls.method.id,
                "sequence": 1,
                "duration_minutes": 20,
                "instruction": "Weigh",
                "location_id": cls.room.id,
            }
        )
        (cls.tester | cls.head).user_id.partner_id.email = "lab@anphu.example"

    def propose(self, test=None):
        """The booking the department's plan proposes for the test once it is assigned to the tester."""
        test = test or self.test
        self.testing_task(test, self.tester)
        return test.booking_ids

    def notices(self, event, record):
        """The messages of the event about the record, and the partners they went to."""
        messages = self.env[MODEL_MAIL_MESSAGE].search(
            [("model", "=", record._name), ("res_id", "=", record.id), ("subtype_id", "=", self.env.ref(event).id)]
        )
        return messages, messages.notification_ids.res_partner_id

    def machine_slot(self):
        """The first start at which the machine is free for a run."""
        return self.env[MODEL_MACHINE_BOOKING]._free_slot(self.fast, RUN, self.other_tester, MONDAY + timedelta(days=1))

    def test_approving_reserves_the_tester_the_machine_and_the_rooms_and_tells_the_tester(self):
        booking = self.propose()
        self.assertFalse(booking.calendar_event_id | booking.room_event_ids)
        self.assertFalse(self.notices(APPROVED_EVENT, booking)[0])
        self.assertEqual(self.machine_slot(), MONDAY)

        booking.with_user(self.head.user_id).action_approve()

        self.assertEqual((booking.status, booking.machine_id, booking.starts_at), ("scheduled", self.fast, MONDAY))
        self.assertEqual(booking.calendar_event_id.user_id, self.tester.user_id)
        self.assertEqual(booking.room_event_ids.location_id, self.room)
        self.assertEqual(self.machine_slot(), MONDAY + RUN)
        messages, partners = self.notices(APPROVED_EVENT, booking)
        self.assertEqual(partners, self.tester.user_id.partner_id)
        self.assertIn(booking.display_name, messages.body or "")

    def test_approving_an_unchanged_proposal_does_not_recalculate_unrelated_proposals(self):
        booking = self.propose()
        bookings = self.env[MODEL_MACHINE_BOOKING]
        with patch.object(type(bookings), "_plan"):
            for _ in range(32):
                test = self.new_test(MONDAY + timedelta(days=2))
                self.testing_task(test, self.other_tester)
        plan_started = times().elapsed
        bookings._plan(self.department)
        plan_elapsed = times().elapsed - plan_started
        proposals = bookings.search([("status", "=", "proposed"), ("department_id", "=", self.department.id)])
        proposal_count = len(proposals)
        self.assertEqual(proposal_count, 33)

        original_plan = type(bookings)._plan
        plan_calls = 0

        def count_plan_calls(model, departments):
            nonlocal plan_calls
            plan_calls += 1
            return original_plan(model, departments)

        with patch.object(type(bookings), "_plan", new=count_plan_calls):
            started = times().elapsed
            booking.sample_test_id.with_user(self.head.user_id).action_approve_booking()
            elapsed = times().elapsed - started

        print(f"[scheduler-profile] proposed={proposal_count} action=_plan calls=1 elapsed={plan_elapsed:.2f}s")
        print(
            f"[scheduler-profile] proposed={proposal_count} action=action_approve_booking "
            f"plan_calls={plan_calls} elapsed={elapsed:.2f}s"
        )
        self.assertEqual(plan_calls, 0)

    def test_approving_without_a_current_proposal_recalculates_the_plan(self):
        test = self.new_test(MONDAY + timedelta(minutes=10))
        self.propose(test)
        bookings = self.env[MODEL_MACHINE_BOOKING]
        original_plan = type(bookings)._plan
        plan_calls = 0

        def count_plan_calls(model, departments):
            nonlocal plan_calls
            plan_calls += 1
            return original_plan(model, departments)

        with patch.object(type(bookings), "_plan", new=count_plan_calls):
            with self.assertRaisesRegex(UserError, "No machine can finish"):
                test.with_user(self.head.user_id).action_approve_booking()

        self.assertEqual(plan_calls, 1)

    def test_the_tester_does_not_reserve_their_own_booking(self):
        booking = self.propose()

        with self.assertRaises(AccessError):
            booking.with_user(self.tester.user_id).action_approve()
        with self.assertRaises(AccessError):
            self.test.with_user(self.tester.user_id).action_approve_booking()
        with self.assertRaisesRegex(UserError, "head of the department approves"):
            booking.with_user(self.tester.user_id).write({"status": "scheduled"})

        self.assertEqual(booking.status, "proposed")
        self.assertFalse(booking.calendar_event_id | booking.room_event_ids)
        self.assertFalse(self.notices(APPROVED_EVENT, booking)[0])

    def test_the_head_reserves_a_booking_only_by_approving_it(self):
        booking = self.propose()
        head_bookings = self.env[MODEL_MACHINE_BOOKING].with_user(self.head.user_id)

        with self.assertRaisesRegex(UserError, "head of the department approves"):
            booking.with_user(self.head.user_id).write({"status": "scheduled"})
        with self.assertRaisesRegex(UserError, "head of the department approves"):
            head_bookings.create(
                {
                    "sample_test_id": self.test.id,
                    "machine_id": self.fast.id,
                    "starts_at": MONDAY + timedelta(hours=3),
                    "ends_at": MONDAY + timedelta(hours=4),
                    "status": "scheduled",
                }
            )

        self.assertEqual(booking.status, "proposed")
        self.assertFalse(booking.calendar_event_id)

    def test_only_the_head_of_the_bookings_department_approves_it(self):
        booking = self.propose()
        other_head = self.create_person(
            "Vo Thi Hanh",
            self.microbiology,
            "hanh.vo",
            permissions=("machine_booking.read.own_department", "machine_booking.edit.own_department"),
        )

        with self.assertRaises(AccessError):
            booking.with_user(other_head.user_id).action_approve()

        self.assertEqual(booking.status, "proposed")

    def test_a_person_who_edits_the_bookings_of_every_department_approves_it(self):
        booking = self.propose()
        lab_head = self.create_person(
            "Vo Thi Hanh",
            self.microbiology,
            "hanh.vo",
            permissions=("machine_booking.read.all", "machine_booking.edit.all"),
        )

        booking.with_user(lab_head.user_id).action_approve()

        self.assertEqual((booking.status, booking.machine_id, booking.starts_at), ("scheduled", self.fast, MONDAY))
        self.assertEqual(self.notices(APPROVED_EVENT, booking)[1], self.tester.user_id.partner_id)

    def test_a_booking_the_plan_cannot_fit_before_the_due_date_goes_to_the_head_for_review_and_is_not_approved(self):
        test = self.new_test(MONDAY + timedelta(minutes=10))
        booking = self.propose(test)

        self.assertFalse(booking.starts_at)
        self.assertTrue(test.at_risk and test.outsourcing_suggested)
        self.assertIn(self.head.user_id.partner_id, self.notices(AT_RISK_EVENT, test)[1])
        with self.assertRaisesRegex(UserError, "No machine can finish"):
            booking.with_user(self.head.user_id).action_approve()

        self.assertEqual(booking.status, "proposed")
        self.assertFalse(booking.calendar_event_id)

    def test_a_due_date_changed_to_before_the_slot_ends_takes_the_booking_to_the_head_for_review(self):
        booking = self.propose()
        self.assertEqual(booking.starts_at, MONDAY)

        self.test.write({"due_date": MONDAY + timedelta(minutes=30), "due_date_reason": "The customer asked"})

        self.assertFalse(booking.starts_at)
        with self.assertRaisesRegex(UserError, "No machine can finish"):
            booking.with_user(self.head.user_id).action_approve()
        self.assertEqual(booking.status, "proposed")

    def test_a_room_taken_meanwhile_leaves_the_machine_and_the_tester_unreserved(self):
        booking = self.propose()
        self.book(self.room, MONDAY, hours=0.25)

        with self.assertRaisesRegex(UserError, "was taken meanwhile"):
            booking.with_user(self.head.user_id).action_approve()

        self.assertEqual(booking.status, "proposed")
        self.assertFalse(booking.calendar_event_id | booking.room_event_ids)
        self.assertEqual(self.machine_slot(), MONDAY)
        self.assertFalse(self.notices(APPROVED_EVENT, booking)[0])

    def test_a_head_who_is_the_tester_is_not_told_of_their_own_approval(self):
        task = self.testing_task(self.test, self.head)
        booking = self.test.booking_ids

        booking.with_user(self.head.user_id).action_approve()

        self.assertEqual((booking.status, task.assignee_id), ("scheduled", self.head))
        self.assertFalse(self.notices(APPROVED_EVENT, booking)[1])
