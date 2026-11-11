from odoo.tests import tagged

from .schedule_race_case import ScheduleRaceCase
from .scheduling_committed_case import HEAD_PERMISSIONS
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST


@tagged("post_install", "-at_install")
class TestBookingRaces(ScheduleRaceCase):
    """The tester starting their scheduled booking while it is cancelled: by the tester, or with the whole test by the
    head. Only a scheduled booking starts and only a queued or scheduled one is cancelled, while cancelling a test
    cancels its running booking too."""

    def setUp(self):
        super().setUp()

        def scheduled(env):
            self.grant(env, 1, (*HEAD_PERMISSIONS, "sample_test_edit_all"))
            self.assign(env)
            env[MODEL_SAMPLE_TEST].browse(self.test_ids[0]).with_user(self.user_ids[0]).action_schedule()

        self.committed(scheduled)
        self.before = self.committed(self.graph)
        self.assert_consistent_booking(self.before, 0)

    def assert_cancelled_with_its_events(self, graph):
        [booking] = graph["bookings"]
        self.assertEqual(booking["status"], "cancelled")
        self.assertFalse(graph["events"])
        self.assertEqual((graph["tasks"][0]["planned_start"], graph["tasks"][0]["planned_end"]), (False, False))

    def assert_running(self, graph):
        [booking] = graph["bookings"]
        [scheduled] = self.before["bookings"]
        self.assertEqual(booking["status"], "in_progress")
        self.assertEqual((booking["starts_at"], booking["ends_at"]), (scheduled["starts_at"], scheduled["ends_at"]))
        self.assertEqual(graph["tests"][0]["status"], "testing")
        self.assertEqual(len(graph["events"]), 2, graph)

    def test_a_cancel_racing_a_committed_start_is_refused_and_the_booking_runs(self):
        outcomes = self.race(
            self.booking_action("action_start"),
            self.booking_action("action_cancel"),
            boundaries={"first": self.setting("in_progress"), "second": self.setting("cancelled")},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"], ("refused", "Only a queued or scheduled booking can be cancelled."))
        self.assert_retried_on_conflict("second")
        graph = self.committed(self.graph)
        self.assert_running(graph)
        self.assertEqual(graph["tasks"][0]["status"], "assigned")
        self.committed(self.assert_committed_invariants)

    def test_a_start_racing_a_committed_cancel_is_refused_and_the_booking_stays_cancelled(self):
        outcomes = self.race(
            self.booking_action("action_start"),
            self.booking_action("action_cancel"),
            boundaries={"first": self.setting("in_progress"), "second": self.setting("cancelled")},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        self.assertEqual(outcomes["first"], ("refused", "Only a scheduled booking can be started."))
        self.assert_retried_on_conflict("first")
        graph = self.committed(self.graph)
        self.assert_cancelled_with_its_events(graph)
        self.assertEqual((graph["tests"][0]["status"], graph["tasks"][0]["status"]), ("assigned", "assigned"))
        self.committed(self.assert_committed_invariants)

    def test_a_test_cancelled_after_its_booking_starts_cancels_the_running_booking(self):
        outcomes = self.race(
            self.booking_action("action_start"),
            self.cancel_test,
            boundaries={"first": self.setting("in_progress"), "second": self.cancelling()},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assert_retried_on_conflict("second")
        graph = self.committed(self.graph)
        self.assertEqual((graph["tests"][0]["status"], graph["tasks"][0]["status"]), ("cancelled", "cancelled"))
        self.assert_cancelled_with_its_events(graph)
        self.committed(self.assert_committed_invariants)

    def test_a_start_racing_a_committed_test_cancellation_is_refused(self):
        outcomes = self.race(
            self.booking_action("action_start"),
            self.cancel_test,
            boundaries={"first": self.setting("in_progress"), "second": self.cancelling()},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        self.assertEqual(outcomes["first"], ("refused", "Only a scheduled booking can be started."))
        self.assert_retried_on_conflict("first")
        graph = self.committed(self.graph)
        self.assertEqual((graph["tests"][0]["status"], graph["tasks"][0]["status"]), ("cancelled", "cancelled"))
        self.assert_cancelled_with_its_events(graph)
        self.committed(self.assert_committed_invariants)
