from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .plan_revision_case import AFTERNOON, EVENING, RUN, THURSDAY, TUESDAY, WEDNESDAY, PlanRevisionCase


@freeze_time(TUESDAY)
@tagged("post_install", "-at_install")
class TestPinnedBookings(PlanRevisionCase):
    """A booking the head moves by hand is pinned, so a plan revision never moves it."""

    def test_a_booking_is_pinned_when_the_head_moves_it_and_not_when_its_tester_does(self):
        self.assertFalse(self.z.is_pinned)

        self.z.with_user(self.tester.user_id).write({"starts_at": THURSDAY})
        self.assertEqual((self.z.starts_at, self.z.is_pinned), (THURSDAY, False))

        self.z.with_user(self.head.user_id).write({"starts_at": THURSDAY + timedelta(hours=4)})
        self.assertEqual((self.z.starts_at, self.z.is_pinned), (THURSDAY + timedelta(hours=4), True))

    def test_a_booking_stays_pinned_while_it_runs_and_is_unpinned_when_cancelled(self):
        self.z.with_user(self.head.user_id).write({"starts_at": THURSDAY})
        self.assertTrue(self.z.is_pinned)

        self.z.with_user(self.head.user_id).action_cancel()

        self.assertEqual((self.z.status, self.z.is_pinned), ("cancelled", False))

    def test_a_revision_reports_a_conflict_instead_of_moving_a_pinned_booking(self):
        # The head put Z in the morning by hand, so urgent X cannot have it.
        self.z.with_user(self.head.user_id).write({"starts_at": WEDNESDAY})
        self.assertTrue(self.z.is_pinned)
        x_test, _x = self.urgent_arrives()

        revision = self.open_revision()
        self.assertEqual(self.moves(revision), {self.z: ("conflict", THURSDAY), self.y: ("held_back", THURSDAY)})

        with self.assertRaisesRegex(UserError, "No move waits for your approval"):
            revision.with_user(self.head.user_id).action_approve()
        self.assertEqual((self.z.starts_at, self.z.is_pinned, self.y.starts_at), (WEDNESDAY, True, AFTERNOON))
        self.assertTrue(x_test.at_risk)

    def test_a_pinned_booking_stays_while_the_other_bookings_make_room(self):
        self.z.with_user(self.head.user_id).write({"starts_at": WEDNESDAY})
        self.record_overtime()
        x_test, x = self.urgent_arrives()

        # The morning is pinned, so only Y moves, to the evening, and X takes the afternoon it leaves.
        revision = self.open_revision()
        self.assertEqual(self.moves(revision), {self.y: ("proposed", EVENING)})

        revision.with_user(self.head.user_id).action_approve()

        self.assertEqual((self.z.starts_at, self.z.is_pinned, self.y.starts_at), (WEDNESDAY, True, EVENING))
        self.assertEqual((x.starts_at, x.ends_at), (AFTERNOON, AFTERNOON + RUN))
        self.assertFalse(x_test.at_risk)

    def test_a_running_booking_is_never_moved(self):
        self.z.with_user(self.tester.user_id).action_start()
        self.assertEqual(self.z.status, "in_progress")
        self.record_overtime()

        self.urgent_arrives()

        revision = self.open_revision()
        self.assertNotIn(self.z, revision.move_ids.booking_id)
        self.assertEqual((self.z.status, self.z.starts_at), ("in_progress", WEDNESDAY))
