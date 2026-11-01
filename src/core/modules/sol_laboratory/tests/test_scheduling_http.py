from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .scheduling_committed_case import HEAD_PERMISSIONS
from .scheduling_http_case import SchedulingHttpCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_SAMPLE_TEST, MODEL_TASK


@tagged("post_install", "-at_install")
class TestSchedulingHttp(SchedulingHttpCase):
    def test_a_failed_schedule_batch_rolls_back_its_first_booking(self):
        self.committed(self.assign)
        self.committed(self.keep_foreign_queue)
        before = self.committed(self.graph)
        browser = self.sign_in()

        answer = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [self.test_ids])

        self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.UserError", answer)
        self.assertIn("before scheduling it", answer["error"]["data"]["message"])
        self.assertEqual(self.committed(self.graph), before)
        self.committed(self.assert_committed_invariants)
        requested_at = fields.Datetime.now()
        recovered = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [[self.test_ids[0]]])
        self.assertNotIn("error", recovered, recovered)
        after = self.committed(self.graph)
        self.assertEqual(len(after["bookings"]), 1)
        self.assertEqual(len(after["events"]), 2)
        self.assert_consistent_booking(after, 0)
        [booking] = after["bookings"]
        self.assertGreaterEqual(booking["starts_at"], requested_at)
        self.assertEqual(booking["ends_at"] - booking["starts_at"], timedelta(minutes=45))
        self.assertEqual((after["tasks"][1], after["tests"][1]), (before["tasks"][1], before["tests"][1]))
        self.committed(self.assert_committed_invariants)

    def test_a_failed_claim_batch_rolls_back_its_first_claim(self):
        self.committed(self.assign)
        before = self.committed(self.graph)
        self.assertEqual((before["tasks"][1]["status"], before["tasks"][1]["assignee_id"]), ("open", False))
        self.assertEqual(before["tests"][1]["status"], "waiting")
        browser = self.sign_in(1)

        answer = self.call(browser, MODEL_TASK, "action_claim", [[self.task_ids[1], self.task_ids[0]]])

        self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.UserError", answer)
        self.assertIn("already claimed", answer["error"]["data"]["message"])
        self.assertEqual(self.committed(self.graph), before)
        self.committed(self.assert_committed_invariants)
        recovered = self.call(browser, MODEL_TASK, "action_claim", [[self.task_ids[1]]])
        self.assertNotIn("error", recovered, recovered)
        after = self.committed(self.graph)
        self.assertEqual(after["tasks"][1]["status"], "assigned")
        self.assertEqual(after["tasks"][1]["assignee_id"][0], self.person_ids[1])
        self.assertEqual(after["tasks"][1]["assigned_by_id"][0], self.person_ids[1])
        self.assertEqual(after["tests"][1]["status"], "assigned")
        self.assertEqual((after["tasks"][0], after["tests"][0]), (before["tasks"][0], before["tests"][0]))
        self.assertFalse(after["bookings"])
        self.assertFalse(after["events"])
        claims = [entry for entry in after["audit"] if entry not in before["audit"]]
        self.assertEqual([(entry["document_id"], entry["action"]) for entry in claims], [(self.task_ids[1], "edit")])
        self.committed(self.assert_committed_invariants)

    def test_scheduling_internals_are_refused_over_rpc_even_to_the_head_who_may_cancel_the_booking(self):
        def prepare(env):
            # Before the head's first request: the server process caches each user's groups.
            self.grant(env, 1, HEAD_PERMISSIONS)
            self.assign(env)
            env[MODEL_SAMPLE_TEST].browse(self.test_ids[0]).with_user(self.user_ids[0]).action_schedule()
            return env[MODEL_MACHINE_BOOKING].search([("sample_test_id", "=", self.test_ids[0])]).id

        self.committed(self.keep_foreign_queue)
        booking_id = self.committed(prepare)
        before = self.committed(self.graph)
        self.assert_consistent_booking(before, 0)
        tester, head = self.sign_in(0), self.sign_in(1)
        later = str(before["bookings"][0]["starts_at"] + timedelta(days=1))
        internals = {
            "_set": [[booking_id], {"status": "cancelled"}],
            "_move": [[booking_id], later],
            "_process_queue": [[]],
            "_requeue": [[], [self.machine_id]],
            "_follow_assignment": [[], [self.task_ids[0]]],
            "_recommend": [[], self.test_ids[0], self.person_ids[1], self.department_id],
        }
        for actor, browser in (("head", head), ("tester", tester)):
            for method, args in internals.items():
                with self.subTest(actor=actor, method=method):
                    answer = self.call(browser, MODEL_MACHINE_BOOKING, method, args)
                    self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.AccessError", answer)
                    self.assertEqual(
                        answer["error"]["data"]["message"],
                        f"Private methods (such as '{MODEL_MACHINE_BOOKING}.{method}') cannot be called remotely.",
                    )
                    self.assertEqual(self.committed(self.graph), before)

        cancelled = self.call(head, MODEL_MACHINE_BOOKING, "action_cancel", [[booking_id]])

        self.assertNotIn("error", cancelled, cancelled)
        after = self.committed(self.graph)
        [booking] = after["bookings"]
        self.assertEqual(booking["status"], "cancelled")
        self.assertFalse(after["events"])
        self.assertEqual(after["tasks"][0]["assignee_id"][0], self.person_ids[0])
        self.assertEqual((after["tasks"][1], after["tests"][1]), (before["tasks"][1], before["tests"][1]))
        self.committed(self.assert_committed_invariants)

    def test_a_schedule_sent_again_after_it_committed_is_refused_and_changes_nothing(self):
        self.committed(self.assign)
        self.committed(self.keep_foreign_queue)
        browser = self.sign_in()
        first = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [[self.test_ids[0]]])
        self.assertNotIn("error", first, first)
        scheduled = self.committed(self.graph)
        self.assert_consistent_booking(scheduled, 0)
        counts = self.committed(self.table_counts)

        # The client never saw the first answer, so it sends the same request again.
        again = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [[self.test_ids[0]]])

        self.assertEqual(again["error"]["data"]["name"], "odoo.exceptions.UserError", again)
        self.assertRegex(again["error"]["data"]["message"], r"^.+ is already waiting for or holding a machine\.$")
        self.assertEqual(self.committed(self.graph), scheduled)
        self.assertEqual(self.committed(self.table_counts), counts)
        self.committed(self.assert_committed_invariants)
