from odoo.tests import tagged

from .scheduling_http_case import SchedulingHttpCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK


@tagged("post_install", "-at_install")
class TestSchedulingHttp(SchedulingHttpCase):
    def test_a_failed_schedule_batch_rolls_back_its_first_booking(self):
        self.committed(self.assign)
        before = self.committed(self.graph)
        browser = self.sign_in()

        answer = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [self.test_ids])

        self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.UserError", answer)
        self.assertIn("before scheduling it", answer["error"]["data"]["message"])
        self.assertEqual(self.committed(self.graph), before)
        recovered = self.call(browser, MODEL_SAMPLE_TEST, "action_schedule", [[self.test_ids[0]]])
        self.assertNotIn("error", recovered, recovered)
        after = self.committed(self.graph)
        self.assertEqual(len(after["bookings"]), 1)
        self.assertEqual(len(after["events"]), 2)
        self.assertEqual(after["tasks"][1], before["tasks"][1])

    def test_a_failed_claim_batch_rolls_back_its_first_claim(self):
        self.committed(self.assign)
        before = self.committed(self.graph)
        browser = self.sign_in(1)

        answer = self.call(browser, MODEL_TASK, "action_claim", [[self.task_ids[1], self.task_ids[0]]])

        self.assertEqual(answer["error"]["data"]["name"], "odoo.exceptions.UserError", answer)
        self.assertIn("already claimed", answer["error"]["data"]["message"])
        self.assertEqual(self.committed(self.graph), before)
        recovered = self.call(browser, MODEL_TASK, "action_claim", [[self.task_ids[1]]])
        self.assertNotIn("error", recovered, recovered)
        after = self.committed(self.graph)
        self.assertEqual(after["tasks"][1]["assignee_id"][0], self.person_ids[1])
        self.assertEqual(after["tasks"][1]["assigned_by_id"][0], self.person_ids[1])
        self.assertEqual(after["tasks"][0], before["tasks"][0])
        self.assertFalse(after["bookings"])
        self.assertFalse(after["events"])
