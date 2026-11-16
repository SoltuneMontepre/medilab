from odoo.tests import tagged

from .result_case import ResultCase

SENT_EVENT = "sol_laboratory.event_test_result_sent"


@tagged("post_install", "-at_install")
class TestTestResultSent(ResultCase):
    """The head of the department that tested a result is told when the result is sent for approval."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department.manager_id = cls.head.employee_id
        cls.head.user_id.notification_type = "inbox"
        cls.microbiology.manager_id = cls.microbiologist.employee_id
        cls.microbiologist.user_id.notification_type = "inbox"

    def messages(self, result):
        return self.env["mail.message"].search(
            [
                ("model", "=", result._name),
                ("res_id", "=", result.id),
                ("subtype_id", "=", self.env.ref(SENT_EVENT).id),
            ]
        )

    def test_sending_a_result_tells_the_head_of_the_department_that_tested_it(self):
        result = self.enter()
        self.assertFalse(self.messages(result))

        self.send(result)

        message = self.messages(result)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.notification_ids.res_partner_id, self.head.user_id.partner_id)
        self.assertIn(result.display_name, message.body)

    def test_the_head_of_another_department_is_not_told(self):
        result = self.enter()
        self.send(result)

        self.assertNotIn(self.microbiologist.user_id.partner_id, self.messages(result).notification_ids.res_partner_id)

    def test_approving_a_result_tells_the_head_nothing_more(self):
        result = self.enter()
        self.send(result)
        self.approve(result)

        self.assertEqual(len(self.messages(result)), 1)

    def test_a_result_sent_again_after_the_tester_withdrew_it_tells_the_head_again(self):
        result = self.enter()
        self.send(result)
        self.as_person(result, self.tester).action_withdraw()
        self.assertEqual(len(self.messages(result)), 1)

        self.send(result)

        messages = self.messages(result)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages.notification_ids.res_partner_id, self.head.user_id.partner_id)

    def test_a_head_who_sends_their_own_result_is_not_told(self):
        self.take_task(self.head)
        result = self.enter(person=self.head)

        self.send(result, self.head)

        self.assertEqual(result.status, "requested")
        self.assertFalse(self.messages(result).notification_ids)

    def test_a_retest_sent_after_a_rejection_tells_the_head(self):
        result = self.enter()
        self.send(result)
        self.as_person(result, self.head).action_reject("The blank read above the limit of detection.")
        self.as_person(self.test._testing_task(), self.tester).action_claim()
        retest = self.enter(value=0.009)

        self.send(retest)

        self.assertEqual(self.messages(retest).notification_ids.res_partner_id, self.head.user_id.partner_id)
