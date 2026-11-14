from odoo.tests import tagged

from .schedule_race_case import ROOM_STEP, ScheduleRaceCase
from .scheduling_committed_case import HEAD_PERMISSIONS
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_SAMPLE_TEST

CANCEL_PERMISSIONS = (*HEAD_PERMISSIONS, "sample_test_edit_all")


@tagged("post_install", "-at_install")
class TestScheduleRaces(ScheduleRaceCase):
    """A schedule racing another scheduling action, the other action's transaction overlapping the schedule's."""

    def test_two_tests_scheduled_at_once_take_the_two_slots_of_the_plan(self):
        self.committed(lambda env: (self.assign(env, 0), self.assign(env, 1)))

        outcomes = self.race(
            self.schedule(0), self.schedule(1), boundaries={"first": self.placing(0), "second": self.placing(1)}
        )

        self.assertEqual({outcome[0] for outcome in outcomes.values()}, {"committed"}, outcomes)
        graph = self.committed(self.graph)
        first, second = sorted(graph["bookings"], key=lambda booking: booking["starts_at"])
        self.assertEqual((first["status"], second["status"]), ("scheduled", "scheduled"), graph)
        self.assertLessEqual(first["ends_at"], second["starts_at"], graph)
        for number in (0, 1):
            self.assert_consistent_booking(graph, number)
        self.committed(self.assert_committed_invariants)

    def proposed(self):
        """The proposed bookings of the fixture's first test, as (person id or False)."""
        return self.committed(
            lambda env: [
                booking.person_id.id
                for booking in env[MODEL_MACHINE_BOOKING].search(
                    [("sample_test_id", "=", self.test_ids[0]), ("status", "=", "proposed")]
                )
            ]
        )

    def test_a_reassignment_committed_while_the_first_assignee_schedules_returns_the_booking_to_the_plan(self):
        self.committed(lambda env: (self.grant(env, 1, HEAD_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.reassign(1),
            boundaries={"first": self.queueing(), "second": self.reassigning()},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assert_retried_on_conflict("second")
        graph = self.committed(self.graph)
        task, test = graph["tasks"][0], graph["tests"][0]
        self.assertEqual((task["status"], task["assignee_id"][0]), ("assigned", self.person_ids[1]))
        self.assertEqual(test["status"], "assigned")
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.assertEqual(self.proposed(), [self.person_ids[1]])
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_racing_a_committed_reassignment_is_refused_and_books_nothing(self):
        self.committed(lambda env: (self.grant(env, 1, HEAD_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.reassign(1),
            boundaries={"first": self.queueing(), "second": self.reassigning()},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        self.assertEqual(outcomes["first"][0], "refused", outcomes)
        self.assert_retried_on_conflict("first")
        graph = self.committed(self.graph)
        task, test = graph["tasks"][0], graph["tests"][0]
        self.assertEqual((task["status"], task["assignee_id"][0]), ("assigned", self.person_ids[1]))
        self.assertEqual(test["status"], "assigned")
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.committed(self.assert_committed_invariants)

    def test_a_cancellation_after_a_committed_schedule_cancels_the_new_booking(self):
        self.committed(lambda env: (self.grant(env, 1, CANCEL_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.cancel_test,
            boundaries={"first": self.queueing(), "second": self.cancelling()},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assert_retried_on_conflict("second")
        graph = self.committed(self.graph)
        self.assertEqual((graph["tests"][0]["status"], graph["tasks"][0]["status"]), ("cancelled", "cancelled"))
        [booking] = graph["bookings"]
        self.assertEqual(booking["status"], "cancelled")
        self.assertFalse(graph["events"])
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_racing_a_committed_cancellation_is_refused_and_books_nothing(self):
        self.committed(lambda env: (self.grant(env, 1, CANCEL_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.cancel_test,
            boundaries={"first": self.queueing(), "second": self.cancelling()},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        self.assertEqual(outcomes["first"][0], "refused", outcomes)
        self.assert_retried_on_conflict("first")
        graph = self.committed(self.graph)
        self.assertEqual((graph["tests"][0]["status"], graph["tasks"][0]["status"]), ("cancelled", "cancelled"))
        # The proposed booking left the plan with the test.
        self.assertEqual([booking["status"] for booking in graph["bookings"]], ["cancelled"])
        self.assertFalse(graph["events"])
        self.committed(self.assert_committed_invariants)

    def test_a_return_to_the_queue_after_a_committed_schedule_returns_the_booking_to_the_plan(self):
        self.committed(lambda env: (self.grant(env, 1, HEAD_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.reassign(None),
            boundaries={"first": self.queueing(), "second": self.reassigning()},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assert_retried_on_conflict("second")
        graph = self.committed(self.graph)
        task, test = graph["tasks"][0], graph["tests"][0]
        self.assertEqual((task["status"], task["assignee_id"]), ("open", False))
        self.assertEqual((task["planned_start"], task["planned_end"]), (False, False))
        self.assertEqual(test["status"], "waiting")
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.assertEqual(self.proposed(), [False])
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_racing_a_committed_return_to_the_queue_is_refused_and_books_nothing(self):
        self.committed(lambda env: (self.grant(env, 1, HEAD_PERMISSIONS), self.assign(env, 0)))

        outcomes = self.race(
            self.schedule(0),
            self.reassign(None),
            boundaries={"first": self.queueing(), "second": self.reassigning()},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        self.assertEqual(outcomes["first"][0], "refused", outcomes)
        self.assertIn("before scheduling it", outcomes["first"][1])
        self.assert_retried_on_conflict("first")
        graph = self.committed(self.graph)
        task, test = graph["tasks"][0], graph["tests"][0]
        self.assertEqual((task["status"], task["assignee_id"]), ("open", False))
        self.assertEqual(test["status"], "waiting")
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.committed(self.assert_committed_invariants)

    def test_a_room_booked_by_a_person_after_a_committed_schedule_is_refused(self):
        start = self.room_slot()

        outcomes = self.race(
            self.schedule(0),
            self.book_room(start),
            boundaries={"first": self.booking_rooms(), "second": self.booking_room()},
            commits_first="first",
        )

        self.assert_won_first_time("first")
        self.assertEqual(outcomes["second"][0], "refused", outcomes)
        self.assertEqual(self.race_evidence["conflicts"]["second"], ["EXCLUSION_VIOLATION"], self.race_evidence)
        graph = self.committed(self.graph)
        [booking] = graph["bookings"]
        self.assertEqual((booking["status"], booking["starts_at"]), ("scheduled", start))
        self.assert_consistent_booking(graph, 0)
        self.assertEqual(len(graph["events"]), 2, graph)
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_racing_a_committed_room_booking_books_neither_the_room_nor_the_machine(self):
        start = self.room_slot()
        before = self.committed(self.graph)

        self.race(
            self.schedule(0),
            self.book_room(start),
            boundaries={"first": self.booking_rooms(), "second": self.booking_room()},
            commits_first="second",
        )

        self.assert_won_first_time("second")
        graph = self.committed(self.graph)
        [room] = [event for event in graph["events"] if not event["machine_booking_id"]]
        self.assertEqual(
            (room["start"], room["stop"], room["user_id"][0]), (start, start + ROOM_STEP, self.user_ids[1])
        )
        self.assert_lost_slot("first", 0, start, room["id"], before)

    def room_slot(self):
        """Assign the first test, and return the start the scheduler recommends for it, whose first step books the
        fixture's room."""
        self.committed(self.assign)
        return self.committed(lambda env: env[MODEL_SAMPLE_TEST].browse(self.test_ids[0]).recommended_start)
