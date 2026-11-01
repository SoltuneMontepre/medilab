from odoo.tests import tagged

from .scheduling_committed_case import HEAD_PERMISSIONS
from .scheduling_concurrency_case import SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK

NOTE = "Use the spare column"


@tagged("post_install", "-at_install")
class TestClaimRaces(SchedulingConcurrencyCase):
    """A tester claiming a queued task while the head saves a note on it: the note does not assign the task, so one
    transaction committing before the other leaves it claimed and noted."""

    def setUp(self):
        super().setUp()
        self.committed(lambda env: self.grant(env, 1, HEAD_PERMISSIONS))
        self.before = self.committed(self.graph)
        self.assertEqual((self.before["tasks"][0]["status"], self.before["tasks"][0]["assignee_id"]), ("open", False))

    def claim(self, env):
        task = env[MODEL_TASK].browse(self.task_ids[0])
        # The queue shows the task first: that read takes the transaction's snapshot before the boundary.
        self.assertEqual(task.status, "open")
        task.with_user(self.user_ids[0]).action_claim()

    def save_note(self, env):
        """The head saves a note on the task in its form: the write, then the form reading the task back."""
        task = env[MODEL_TASK].browse(self.task_ids[0]).with_user(self.user_ids[1])
        task.read(["note"])
        task.write({"note": NOTE})
        task.flush_recordset()
        task.web_read({"note": {}})

    def claiming(self):
        task_id = self.task_ids[0]
        return (MODEL_TASK, "action_claim", lambda tasks, _args: tasks.ids == [task_id])

    def noting(self):
        """The note is about to be written."""
        task_id = self.task_ids[0]
        return (MODEL_TASK, "write", lambda tasks, args: tasks.ids == [task_id] and "note" in args[0])

    def noted(self):
        """The note is written and holds the task's row until its transaction ends."""
        task_id = self.task_ids[0]
        return (MODEL_TASK, "web_read", lambda tasks, _args: tasks.ids == [task_id])

    def assert_claimed_and_noted(self):
        graph = self.committed(self.graph)
        task = graph["tasks"][0]
        self.assertEqual((task["status"], task["assignee_id"][0]), ("assigned", self.person_ids[0]))
        self.assertEqual(task["assigned_by_id"][0], self.person_ids[0])
        self.assertEqual(graph["tests"][0]["status"], "assigned")
        self.assertEqual(self.committed(lambda env: env[MODEL_TASK].browse(self.task_ids[0]).note), NOTE)
        self.assertEqual((graph["tasks"][1], graph["tests"][1]), (self.before["tasks"][1], self.before["tests"][1]))
        self.assertFalse(graph["bookings"])
        self.committed(self.assert_committed_invariants)

    def test_a_note_saved_after_a_committed_claim_keeps_the_claim(self):
        outcomes = self.race(
            self.claim,
            self.save_note,
            boundaries={"first": self.claiming(), "second": self.noting()},
            commits_first="first",
        )

        self.assertEqual(outcomes["first"][0], "committed", outcomes)
        self.assertEqual(self.race_evidence["attempts"]["first"], 1, self.race_evidence)
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assertEqual(self.race_evidence["conflicts"]["second"], ["SERIALIZATION_FAILURE"], self.race_evidence)
        self.assert_claimed_and_noted()

    def test_a_claim_after_a_committed_note_claims_the_task(self):
        outcomes = self.race(
            self.claim,
            self.save_note,
            boundaries={"first": self.claiming(), "second": self.noted()},
            commits_first="second",
        )

        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        self.assertEqual(self.race_evidence["attempts"]["second"], 1, self.race_evidence)
        self.assertEqual(outcomes["first"][0], "committed", outcomes)
        self.assertEqual(self.race_evidence["conflicts"]["first"], ["SERIALIZATION_FAILURE"], self.race_evidence)
        self.assert_claimed_and_noted()
