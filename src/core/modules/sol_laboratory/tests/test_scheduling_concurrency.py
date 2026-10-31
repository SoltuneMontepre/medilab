from datetime import timedelta
from itertools import pairwise

from odoo import fields
from odoo.tests import tagged

from .scheduling_concurrency_case import SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_SAMPLE_TEST, MODEL_TASK


@tagged("post_install", "-at_install")
class TestSchedulingConcurrency(SchedulingConcurrencyCase):
    def test_two_people_claiming_one_task_commit_one_assignee(self):
        task_id = self.task_ids[0]
        before = self.committed(self.graph)
        self.assertEqual((before["tasks"][0]["status"], before["tests"][0]["status"]), ("open", "waiting"))

        def claim(number):
            def action(env):
                env[MODEL_TASK].browse(task_id).with_user(self.user_ids[number]).action_claim()
                return self.person_ids[number]

            return action

        outcomes = self.race(
            claim(0), claim(1), MODEL_TASK, "try_lock_for_update", lambda tasks, _args: task_id in tasks.ids
        )
        winners = [person for status, person in outcomes.values() if status == "committed"]
        refusals = [message for status, message in outcomes.values() if status == "refused"]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertEqual(len(refusals), 1, outcomes)
        self.assertIn("already claimed", refusals[0])
        graph = self.committed(self.graph)
        task = graph["tasks"][0]
        self.assertEqual(task["status"], "assigned")
        self.assertEqual(task["assignee_id"][0], winners[0])
        self.assertEqual(task["assigned_by_id"][0], winners[0])
        self.assertEqual(graph["tests"][0]["status"], "assigned")
        self.assertEqual((graph["tasks"][1], graph["tests"][1]), (before["tasks"][1], before["tests"][1]))
        self.assertFalse(graph["bookings"])
        self.assertFalse(graph["events"])
        self.assertFalse(graph["messages"])
        assignments = [
            entry for entry in graph["audit"] if entry["document_id"] == task_id and entry["action"] == "edit"
        ]
        self.assertEqual(len(assignments), 1)
        self.committed(self.assert_committed_invariants)

    def test_two_schedule_requests_for_one_test_commit_one_booking(self):
        self.committed(self.assign)
        test_id = self.test_ids[0]

        def schedule(env):
            env[MODEL_SAMPLE_TEST].browse(test_id).with_user(self.user_ids[0]).action_schedule()

        outcomes = self.race(
            schedule,
            schedule,
            MODEL_MACHINE_BOOKING,
            "create",
            lambda _bookings, args: any(values.get("sample_test_id") == test_id for values in self.values(args[0])),
        )
        self.assertEqual(sorted(status for status, _result in outcomes.values()), ["committed", "refused"], outcomes)
        self.assertIn(
            "already waiting for or holding a machine",
            next(result for status, result in outcomes.values() if status == "refused"),
        )
        graph = self.committed(self.graph)
        self.assertEqual(len(graph["bookings"]), 1, graph)
        self.assert_consistent_booking(graph, 0)
        self.assertEqual(len(graph["events"]), 2, graph)
        self.assertFalse(graph["messages"])

    def test_concurrent_tests_cannot_commit_the_same_machine_slot(self):
        self.committed(lambda env: (self.assign(env, 0), self.assign(env, 1)))
        before = self.committed(self.graph)

        def schedule(number):
            def action(env):
                env[MODEL_SAMPLE_TEST].browse(self.test_ids[number]).with_user(self.user_ids[number]).action_schedule()

            return action

        outcomes = self.race(
            schedule(0),
            schedule(1),
            MODEL_MACHINE_BOOKING,
            "create",
            lambda _bookings, args: any(
                values.get("sample_test_id") in self.test_ids for values in self.values(args[0])
            ),
        )
        graph = self.committed(self.graph)
        self.assertGreaterEqual(sum(status == "committed" for status, _result in outcomes.values()), 1, outcomes)
        self.assertEqual(
            len(graph["bookings"]), sum(status == "committed" for status, _result in outcomes.values()), outcomes
        )
        ordered = sorted(graph["bookings"], key=lambda booking: booking["starts_at"])
        for earlier, later in pairwise(ordered):
            self.assertLessEqual(earlier["ends_at"], later["starts_at"], graph)
        self.assertEqual(len(graph["events"]), 2 * len(ordered), graph)
        for number, task in enumerate(graph["tasks"]):
            if task["planned_start"]:
                self.assert_consistent_booking(graph, number)
            else:
                name = ("first", "second")[number]
                self.assertEqual(outcomes[name][0], "refused")
                self.assertRegex(
                    outcomes[name][1], r"(The machine already has a booking|Scheduling room is already booked)"
                )
                self.assertEqual(task, before["tasks"][number])
                self.assertEqual(graph["tests"][number], before["tests"][number])
                self.assertFalse([event for event in graph["events"] if event["user_id"][0] == self.user_ids[number]])
        self.assertFalse(graph["messages"])

    def test_two_moves_to_one_machine_slot_commit_only_one_move(self):
        def prepare(env):
            for number in (0, 1):
                self.assign(env, number)
                env[MODEL_SAMPLE_TEST].browse(self.test_ids[number]).with_user(self.user_ids[number]).action_schedule()
            bookings = env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "in", self.test_ids)], order="id")
            first = bookings[0]
            earliest = fields.Datetime.now() + timedelta(days=7)
            rooms = first._room_steps(first.sample_test_id.parameter_method_id)
            target = first._free_slot(
                first.machine_id,
                first.ends_at - first.starts_at,
                first.person_id,
                earliest + timedelta(days=7),
                earliest,
                first,
                rooms=rooms,
            )
            self.assertTrue(target)
            return bookings.ids, target

        booking_ids, target = self.committed(prepare)
        before = self.committed(self.graph)

        def move(number):
            return lambda env: (
                env[MODEL_MACHINE_BOOKING]
                .browse(booking_ids[number])
                .with_user(self.user_ids[number])
                .write({"starts_at": target})
            )

        outcomes = self.race(
            move(0),
            move(1),
            MODEL_MACHINE_BOOKING,
            "_set",
            lambda bookings, args: bool(set(bookings.ids) & set(booking_ids)) and args[0].get("starts_at") == target,
        )
        self.assertEqual(sorted(status for status, _result in outcomes.values()), ["committed", "refused"], outcomes)
        refusal = next(result for status, result in outcomes.values() if status == "refused")
        self.assertRegex(refusal, r"(The machine already has a booking|Scheduling room is already booked)")
        after = self.committed(self.graph)
        self.assertEqual(len(after["bookings"]), 2)
        self.assertEqual(len(after["events"]), 4)
        for number, name in enumerate(("first", "second")):
            self.assert_consistent_booking(after, number)
            before_booking = next(booking for booking in before["bookings"] if booking["id"] == booking_ids[number])
            after_booking = next(booking for booking in after["bookings"] if booking["id"] == booking_ids[number])
            if outcomes[name][0] == "committed":
                self.assertEqual(after_booking["starts_at"], target)
            else:
                self.assertEqual(after_booking, before_booking)
                self.assertEqual(after["tasks"][number], before["tasks"][number])
                protected = {before_booking["calendar_event_id"][0], *before_booking["room_event_ids"]}
                self.assertEqual(
                    [event for event in after["events"] if event["id"] in protected],
                    [event for event in before["events"] if event["id"] in protected],
                )
