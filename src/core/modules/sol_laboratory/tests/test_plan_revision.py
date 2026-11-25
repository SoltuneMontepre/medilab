from datetime import datetime

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .assertions import assert_instance
from .plan_revision_case import (
    AFTERNOON,
    EVENING,
    MOVED_EVENT,
    RUN,
    THURSDAY,
    TUESDAY,
    WEDNESDAY,
    PlanRevisionCase,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_MAIL_MESSAGE, MODEL_PLAN_REVISION


@freeze_time(TUESDAY)
@tagged("post_install", "-at_install")
class TestPlanRevision(PlanRevisionCase):
    """The GC-01 example of the scheduling spec: urgent X needs the slots of Z and Y."""

    def notices(self, booking):
        return self.env[MODEL_MAIL_MESSAGE].search(
            [
                ("model", "=", booking._name),
                ("res_id", "=", booking.id),
                ("subtype_id", "=", self.env.ref(MOVED_EVENT).id),
            ]
        )

    def test_the_example_starts_with_z_and_y_in_the_two_intervals_of_wednesday(self):
        self.assertEqual((self.z.starts_at, self.z.ends_at), (WEDNESDAY, WEDNESDAY + RUN))
        self.assertEqual((self.y.starts_at, self.y.ends_at), (AFTERNOON, AFTERNOON + RUN))
        self.assertEqual(self.z_test.due_date, self.y_test.due_date)
        self.assertEqual(assert_instance(self.z_test.due_date, datetime).date(), WEDNESDAY.date())

    def test_a_move_that_would_pass_its_due_date_is_held_back_and_the_rest_is_recalculated_without_it(self):
        x_test, x = self.urgent_arrives()

        revision = self.open_revision()
        # Y's move to Thursday morning passes its due date, so it is held back; recalculated without it, Z could only
        # go to Thursday morning, which passes its own, so it is held back too.
        self.assertEqual(self.moves(revision), {self.z: ("held_back", THURSDAY), self.y: ("held_back", THURSDAY)})
        self.assertEqual(
            (self.z.status, self.z.starts_at, self.y.status, self.y.starts_at),
            ("scheduled", WEDNESDAY, "scheduled", AFTERNOON),
        )
        # GC-01 has no Wednesday interval left, so X is flagged at risk with only Thursday morning to go to.
        self.assertFalse(x.starts_at)
        self.assertTrue(x_test.at_risk)
        self.assertIn("after its internal due date", str(revision.reason))
        self.assertIn(x.display_name, str(revision.reason))
        for move in revision.move_ids:
            self.assertEqual(
                (move.department_id, move.previous_starts_at), (self.department, move.booking_id.starts_at)
            )
            self.assertGreater(
                assert_instance(move.ends_at, datetime), assert_instance(move.sample_test_id.due_date, datetime)
            )

    def test_nothing_that_is_held_back_can_be_approved(self):
        self.urgent_arrives()
        revision = self.open_revision()

        with self.assertRaisesRegex(UserError, "No move waits for your approval"):
            revision.with_user(self.head.user_id).action_approve()

        self.assertEqual(revision.status, "proposed")
        self.assertEqual((self.z.starts_at, self.y.starts_at), (WEDNESDAY, AFTERNOON))

    def test_overtime_makes_room_and_the_head_approves_the_revision_without_asking_a_customer(self):
        x_test, x = self.urgent_arrives()
        held = self.open_revision()

        self.record_overtime()

        # The recalculation puts X in the morning, Z in the afternoon and Y in the evening, all before Wednesday ends.
        revision = self.open_revision()
        self.assertEqual(held.status, "cancelled")
        self.assertEqual(self.moves(revision), {self.z: ("proposed", AFTERNOON), self.y: ("proposed", EVENING)})
        self.assertEqual((self.z.starts_at, self.y.starts_at), (WEDNESDAY, AFTERNOON))
        # The live plan puts X in the evening OverTime, but the revision gives it the earliest slot.
        self.assertEqual(x.starts_at, EVENING)
        for move in revision.move_ids:
            self.assertLessEqual(
                assert_instance(move.ends_at, datetime), assert_instance(move.sample_test_id.due_date, datetime)
            )
            self.assertEqual(str(move.committed_date), "2026-10-16")

        revision.with_user(self.head.user_id).action_approve()

        self.assertEqual(revision.status, "applied")
        self.assertEqual({move.status for move in revision.move_ids}, {"applied"})
        self.assertEqual((self.z.starts_at, self.z.ends_at), (AFTERNOON, AFTERNOON + RUN))
        self.assertEqual((self.y.starts_at, self.y.ends_at), (EVENING, EVENING + RUN))
        self.assertEqual((x.status, x.starts_at), ("proposed", WEDNESDAY))
        self.assertFalse(x_test.at_risk)
        self.assertEqual(str(self.z_test.sample_id.request_id.committed_date), "2026-10-16")
        self.assertEqual(str(self.y_test.sample_id.request_id.committed_date), "2026-10-16")
        for booking in (self.z, self.y):
            self.assertEqual(booking.calendar_event_id.start, booking.starts_at)
        # The tester is told of each moved booking; X is then approved on the freed morning.
        self.assertEqual(self.notices(self.z).notification_ids.res_partner_id, self.tester.user_id.partner_id)
        self.assertTrue(self.notices(self.y))
        x.with_user(self.head.user_id).action_approve()
        self.assertEqual((x.status, x.starts_at), ("scheduled", WEDNESDAY))
        self.assert_schedule_invariants(x_test | self.z_test | self.y_test)

    def test_the_customers_agreement_to_a_later_date_lets_the_held_back_move_through_a_new_revision(self):
        self.urgent_arrives()
        held = self.open_revision()
        self.assertEqual(self.moves(held)[self.y][0], "held_back")

        # Sales records the customer's agreement by changing the expected return date of Y's test request.
        self.y_test.sample_id.request_id.committed_date = "2026-10-20"

        revision = self.open_revision()
        self.assertEqual(held.status, "cancelled")
        self.assertEqual(self.moves(revision), {self.z: ("proposed", AFTERNOON), self.y: ("proposed", THURSDAY)})
        self.assertEqual((self.y.starts_at, self.z.starts_at), (AFTERNOON, WEDNESDAY))

        revision.with_user(self.head.user_id).action_approve()

        self.assertEqual((self.z.starts_at, self.y.starts_at), (AFTERNOON, THURSDAY))
        self.assertLessEqual(self.y.ends_at, self.y_test.due_date)

    def test_no_booking_moves_past_its_internal_due_date_by_any_revision(self):
        self.urgent_arrives()
        self.record_overtime()
        self.open_revision().with_user(self.head.user_id).action_approve()

        for booking in (self.z, self.y):
            self.assertLessEqual(
                assert_instance(booking.ends_at, datetime),
                assert_instance(booking.sample_test_id.due_date, datetime),
            )
        applied = self.env[MODEL_PLAN_REVISION].search([("status", "=", "applied")]).move_ids
        self.assertTrue(applied)
        for move in applied:
            self.assertLessEqual(
                assert_instance(move.ends_at, datetime), assert_instance(move.sample_test_id.due_date, datetime)
            )

    def test_a_recalculation_that_proposes_the_same_keeps_the_open_revision(self):
        self.urgent_arrives()
        revision = self.open_revision()

        self.env[MODEL_MACHINE_BOOKING]._plan(self.department)

        self.assertEqual(self.open_revision(), revision)
        self.assertEqual(revision.status, "proposed")

    def test_urgent_work_that_needs_no_scheduled_slot_gets_no_revision(self):
        # With no scheduled booking in its way, urgent work is just placed first in the plan.
        self.z._set({"status": "cancelled"})
        self.y._set({"status": "cancelled"})

        self.urgent_arrives()

        self.assertFalse(self.env[MODEL_PLAN_REVISION].search([("department_id", "=", self.department.id)]))
