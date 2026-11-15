from odoo.tests import tagged

from .scheduling_concurrency_case import SchedulingConcurrencyCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_AUTHORIZATION, MODEL_TASK


@tagged("post_install", "-at_install")
class TestParameterAuthorizationRaces(SchedulingConcurrencyCase):
    """The first person is no longer authorized for the parameter; both claim the same queued task at once."""

    def setUp(self):
        super().setUp()
        self.committed(
            lambda env: env[MODEL_PARAMETER_AUTHORIZATION].search([("person_id", "=", self.person_ids[0])]).unlink()
        )

    def claimer(self, number):
        def claim(env):
            task = env[MODEL_TASK].browse(self.task_ids[0])
            self.assertEqual(task.status, "open")
            task.with_user(self.user_ids[number]).action_claim()

        return claim

    def test_an_unauthorized_claim_does_not_keep_the_authorized_one_from_claiming(self):
        task_id = self.task_ids[0]
        outcomes = self.race(
            self.claimer(0),
            self.claimer(1),
            MODEL_TASK,
            "action_claim",
            lambda tasks, _args: tasks.ids == [task_id],
        )

        self.assertEqual(outcomes["first"][0], "refused", outcomes)
        self.assertIn("is not authorized to test", outcomes["first"][1])
        self.assertEqual(outcomes["second"][0], "committed", outcomes)
        task = self.committed(self.graph)["tasks"][0]
        self.assertEqual((task["status"], task["assignee_id"][0]), ("assigned", self.person_ids[1]))
        self.committed(self.assert_committed_invariants)
