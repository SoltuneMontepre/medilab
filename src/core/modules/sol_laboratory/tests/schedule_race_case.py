import re
from datetime import timedelta

from odoo.fields import Command

from .scheduling_concurrency_case import RETRIED_CONFLICTS, SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_MACHINE_BOOKING,
    MODEL_SAMPLE_TEST,
    MODEL_SAMPLE_TEST_CANCEL,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
)

REASSIGN_REASON = "The tester is on leave"
CANCEL_REASON = "The customer withdrew the parameter"
ROOM_STEP = timedelta(minutes=30)


class ScheduleRaceCase(SchedulingConcurrencyCase):
    """The actors and production boundaries of the scheduling races, with other tests' queued bookings parked so the
    two transactions meet only on the rows of the race.

    Each action reads what it acts on before its boundary, as its form would, so its snapshot is taken before the
    other transaction can commit (plan Section 8.1, rule 8)."""

    def setUp(self):
        super().setUp()
        self.committed(self.park_foreign_queue)

    # Actions

    def schedule(self, number):
        def action(env):
            env[MODEL_SAMPLE_TEST].browse(self.test_ids[number]).with_user(self.user_ids[number]).action_schedule()

        return action

    def reassign(self, number):
        """The head, the fixture's second person, moves the first task to the fixture's person of the number with the
        assignment wizard, or back to the department's queue when the number is None."""

        def action(env):
            assignee = self.person_ids[number] if number is not None else False
            wizard = (
                env[MODEL_TASK_REASSIGN]
                .with_user(self.user_ids[1])
                .with_context(active_ids=[self.task_ids[0]])
                .create({"assignee_id": assignee, "reason": REASSIGN_REASON})
            )
            self.owned.setdefault(MODEL_TASK_REASSIGN, []).append(wizard.id)
            wizard.action_confirm()

        return action

    def cancel_test(self, env):
        """The head cancels the first test with the cancellation wizard."""
        env[MODEL_SAMPLE_TEST_CANCEL].with_user(self.user_ids[1]).create(
            {"sample_test_id": self.test_ids[0], "reason": CANCEL_REASON}
        ).action_cancel()

    def booking_action(self, method, number=0):
        """The fixture's person of the number takes the action of the method on the first test's booking."""

        def action(env):
            booking = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "=", self.test_ids[0])])
            getattr(booking.with_user(self.user_ids[number]), method)()

        return action

    def book_room(self, start):
        """The second person books the fixture's room for one step's time from the start on their own calendar."""

        def action(env):
            user = self.user_ids[1]
            room = env[MODEL_LOCATION].with_user(user).browse(self.room_id)
            self.assertTrue(room.is_bookable)
            env[MODEL_CALENDAR_EVENT].with_user(user).create(
                {
                    "name": f"Instrument demonstration {self.token}",
                    "start": start,
                    "stop": start + ROOM_STEP,
                    "location_id": room.id,
                    "user_id": user,
                    "partner_ids": [Command.set([self.partner_ids[1]])],
                }
            )

        return action

    # Boundaries

    def queueing(self, number=0):
        """The booking of the fixture's test of the number is about to be created."""
        test_id = self.test_ids[number]
        return (
            MODEL_MACHINE_BOOKING,
            "create",
            lambda _bookings, args: any(values.get("sample_test_id") == test_id for values in self.values(args[0])),
        )

    def setting(self, status, number=0):
        """The booking of the fixture's test of the number is about to take the status."""
        test_id = self.test_ids[number]
        return (
            MODEL_MACHINE_BOOKING,
            "_set",
            lambda bookings, args: args[0].get("status") == status and bookings.sample_test_id.ids == [test_id],
        )

    def placing(self, number=0):
        """The scheduler is about to set the booking of the fixture's test of the number to scheduled."""
        return self.setting("scheduled", number)

    def reassigning(self):
        """The first task's assignee is about to be written."""
        task_id = self.task_ids[0]
        return (MODEL_TASK, "write", lambda tasks, args: tasks.ids == [task_id] and "assignee_id" in args[0])

    def cancelling(self):
        """The first test is about to be cancelled."""
        test_id = self.test_ids[0]
        return (MODEL_SAMPLE_TEST, "action_cancel", lambda tests, _args: tests.ids == [test_id])

    def booking_rooms(self):
        """The scheduled booking of the first test is about to book its rooms."""
        test_id = self.test_ids[0]
        return (
            MODEL_MACHINE_BOOKING,
            "_sync_room_events",
            lambda booking, _args: booking.status == "scheduled" and booking.sample_test_id.id == test_id,
        )

    def booking_room(self):
        """A person, not the scheduler, is about to book the fixture's room."""
        room_id = self.room_id
        return (
            MODEL_CALENDAR_EVENT,
            "create",
            lambda _events, args: any(
                values.get("location_id") == room_id and not values.get("machine_booking_id")
                for values in self.values(args[0])
            ),
        )

    # Checks

    def assert_retried_on_conflict(self, name):
        """The thread's first attempt failed on a database conflict with the other transaction, and it ran again."""
        self.assertGreaterEqual(self.race_evidence["attempts"][name], 2, self.race_evidence)
        self.assertTrue(self.race_evidence["conflicts"][name], self.race_evidence)

    def assert_lost_slot(self, name, number, start, holder_event_id, before):
        """The thread of the name scheduled the fixture's test of the number into the slot from start, which the other
        transaction holds with the calendar event of holder_event_id. Its outcome is AS-IS behaviour, characterized and
        not approved (Q3), so either is accepted:

        - refused when the machine's or the room's exclusion constraint (23P01) stopped its last attempt, with the
          constraint's message, and nothing of its own committed;
        - committed after a deadlock or serialization failure made request retrying run it again, in another slot.

        Any other refusal, error, conflict or broken invariant fails. Returns "refused" or "committed".
        """
        evidence = self.race_evidence
        outcome, conflicts, attempts = (
            evidence["outcomes"][name],
            evidence["conflicts"][name],
            evidence["attempts"][name],
        )
        graph = self.committed(self.graph)
        if outcome[0] == "refused":
            self.assertEqual(conflicts[-1:], ["EXCLUSION_VIOLATION"], evidence)
            self.assertLessEqual(set(conflicts[:-1]), RETRIED_CONFLICTS, evidence)
            self.assertEqual(attempts, len(conflicts), evidence)
            room, holder = self.committed(
                lambda env: (
                    env[MODEL_LOCATION].browse(self.room_id).display_name,
                    env[MODEL_CALENDAR_EVENT].browse(holder_event_id).display_name,
                )
            )
            self.assertRegex(
                outcome[1],
                rf"^The operation cannot be completed: (The machine already has a booking at that time\."
                rf"|{re.escape(room)} is already booked from .+ to .+: {re.escape(holder)}\.)$",
            )
            self.assertFalse([b for b in graph["bookings"] if b["person_id"][0] == self.person_ids[number]], graph)
            self.assertFalse([e for e in graph["events"] if e["user_id"][0] == self.user_ids[number]], graph)
            self.assertEqual(
                (graph["tasks"][number], graph["tests"][number]), (before["tasks"][number], before["tests"][number])
            )
        else:
            self.assertEqual(outcome[0], "committed", evidence)
            self.assertTrue(conflicts, evidence)
            self.assertLessEqual(set(conflicts), RETRIED_CONFLICTS, evidence)
            self.assertEqual(attempts, len(conflicts) + 1, evidence)
            self.assert_consistent_booking(graph, number)
            self.assertNotEqual(graph["tasks"][number]["planned_start"], start)
        self.committed(self.assert_committed_invariants)
        return outcome[0]

    def assert_won_first_time(self, name):
        self.assertEqual(self.race_evidence["outcomes"][name][0], "committed", self.race_evidence)
        self.assertEqual(self.race_evidence["attempts"][name], 1, self.race_evidence)
