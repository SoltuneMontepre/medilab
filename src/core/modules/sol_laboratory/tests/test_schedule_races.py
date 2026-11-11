from odoo.tests import tagged

from .schedule_race_case import ROOM_STEP, ScheduleRaceCase
from .scheduling_committed_case import HEAD_PERMISSIONS
from .scheduling_concurrency_case import NAMES
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST

CANCEL_PERMISSIONS = (*HEAD_PERMISSIONS, "sample_test_edit_all")


@tagged("post_install", "-at_install")
class TestScheduleRaces(ScheduleRaceCase):
    """A schedule racing another scheduling action, the other action's transaction overlapping the schedule's."""

    def test_two_tests_placed_in_one_machine_slot_at_once_leave_one_booking_there(self):
        self.committed(lambda env: (self.assign(env, 0), self.assign(env, 1)))
        before = self.committed(self.graph)

        self.race(self.schedule(0), self.schedule(1), boundaries={"first": self.placing(0), "second": self.placing(1)})

        reached = self.race_evidence["reached"]
        slots = {name: (reached[name][2][0]["machine_id"], reached[name][2][0]["starts_at"]) for name in NAMES}
        self.assertEqual(slots["first"], slots["second"], "Both transactions must place their test in the same slot")
        machine_id, start = slots["first"]
        self.assertEqual(machine_id, self.machine_id)
        graph = self.committed(self.graph)
        holders = [
            booking
            for booking in graph["bookings"]
            if booking["status"] == "scheduled" and booking["starts_at"] == start
        ]
        self.assertEqual(len(holders), 1, graph)
        winner = self.person_ids.index(holders[0]["person_id"][0])
        loser = 1 - winner
        self.assert_won_first_time(NAMES[winner])
        self.assert_consistent_booking(graph, winner)
        [holder_event] = holders[0]["room_event_ids"]
        self.assert_lost_slot(NAMES[loser], loser, start, holder_event, before)

    def test_a_reassignment_committed_while_the_first_assignee_schedules_hands_the_new_booking_over(self):
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
        [booking] = graph["bookings"]
        self.assertEqual((booking["status"], booking["person_id"][0]), ("scheduled", self.person_ids[1]))
        self.assertEqual([event["user_id"][0] for event in graph["events"]], [self.user_ids[1]] * 2)
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
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.committed(self.assert_committed_invariants)

    def test_a_return_to_the_queue_after_a_committed_schedule_cancels_the_new_booking(self):
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
        [booking] = graph["bookings"]
        self.assertEqual(booking["status"], "cancelled")
        self.assertFalse(graph["events"])
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
