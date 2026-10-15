from odoo.exceptions import UserError
from odoo.tests import tagged

from .result_case import ResultCase


@tagged("post_install", "-at_install")
class TestTestResultApproval(ResultCase):
    def test_approving_the_reported_result_closes_the_testing_task(self):
        result = self.enter()
        self.send(result)

        self.approve(result)

        self.assertEqual(result.status, "approved")
        self.assertEqual(self.test.status, "approved")
        self.assertEqual(self.task.status, "done")

    def test_a_sample_is_completed_once_every_result_is_approved(self):
        arsenic = self.add_test()
        lead = self.enter()
        self.send(lead)
        self.approve(lead)
        self.assertEqual(self.sample.status, "testing")

        other = self.enter(test=arsenic)
        self.send(other)
        self.assertEqual(self.sample.status, "awaiting_approval")
        self.assertEqual(self.request.status, "awaiting_approval")
        self.approve(other)

        self.assertEqual(self.sample.status, "completed")
        self.assertEqual(self.request.status, "completed")

    def test_a_head_cannot_approve_a_result_they_entered(self):
        result = self.enter(person=self.head)
        self.send(result, self.other_tester)

        self.assertFalse(self.as_person(result, self.head).approval_can_sign)
        with self.assertRaises(UserError):
            self.approve(result)

    def test_rejecting_keeps_the_result_sends_the_test_back_and_tells_the_tester(self):
        self.tester.user_id.notification_type = "inbox"
        result = self.enter()
        self.send(result)

        self.as_person(result, self.head).action_reject("The blank read above the limit of detection.")

        self.assertEqual(result.status, "rejected")
        self.assertEqual(self.test.status, "testing")
        self.assertEqual(self.task.status, "assigned")
        message = self.env["mail.message"].search([("model", "=", result._name), ("res_id", "=", result.id)])
        self.assertEqual(message.subtype_id, self.env.ref("sol_laboratory.event_test_result_rejected"))
        self.assertIn("The blank read above the limit of detection.", message.body)
        self.assertEqual(message.notification_ids.res_partner_id, self.tester.user_id.partner_id)
        retest = self.enter(value=0.009)
        self.assertTrue(retest.is_reported)
        self.assertEqual(result.status, "rejected")

    def test_the_tester_withdraws_a_sent_result_until_the_head_acts(self):
        result = self.enter()
        self.send(result)

        self.as_person(result, self.tester).action_withdraw()

        self.assertEqual(result.status, "none")
        self.assertEqual(self.test.status, "testing")

    def test_an_approved_or_rejected_result_cannot_be_withdrawn(self):
        arsenic = self.add_test()
        approved = self.enter()
        self.send(approved)
        self.approve(approved)
        rejected = self.enter(test=arsenic)
        self.send(rejected)
        self.as_person(rejected, self.head).action_reject("The duplicate readings differ by 20%.")

        for result in (approved, rejected):
            with self.subTest(status=result.status), self.assertRaises(UserError):
                self.as_person(result, self.head).action_withdraw()
