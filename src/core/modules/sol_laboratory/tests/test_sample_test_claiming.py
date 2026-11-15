from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestSampleTestClaiming(SchedulingCase):
    def as_tester(self, person):
        return self.test.with_user(person.user_id)

    def test_a_tester_claims_the_testing_task_from_its_sample_test(self):
        task = self.testing_task(self.test)
        test = self.as_tester(self.tester)
        self.assertEqual((test.can_claim, test.is_mine), (True, False))

        test.action_claim_testing_task()
        self.assertEqual((task.assignee_id, task.status), (self.tester, "assigned"))
        self.env.invalidate_all()
        self.assertEqual((test.can_claim, test.is_mine), (False, True))

    def test_the_worklist_finds_the_tests_to_claim_then_the_claimed_ones(self):
        self.testing_task(self.test)
        tests = self.env[MODEL_SAMPLE_TEST]
        tester_tests, colleague_tests = tests.with_user(self.tester.user_id), tests.with_user(self.other_tester.user_id)
        self.assertIn(self.test, tester_tests.search([("can_claim", "=", True)]))
        self.assertNotIn(self.test, tester_tests.search([("is_mine", "=", True)]))

        self.as_tester(self.tester).action_claim_testing_task()
        self.assertIn(self.test, tester_tests.search([("is_mine", "=", True)]))
        self.assertNotIn(self.test, tester_tests.search([("can_claim", "=", True)]))
        self.assertNotIn(self.test, colleague_tests.search([("is_mine", "=", True)]))

    def test_a_test_claimed_by_someone_else_cannot_be_claimed(self):
        task = self.testing_task(self.test)
        self.as_tester(self.tester).action_claim_testing_task()

        with self.assertRaises(UserError):
            self.as_tester(self.other_tester).action_claim_testing_task()
        self.assertEqual(task.assignee_id, self.tester)

    def test_a_test_without_a_testing_task_cannot_be_claimed(self):
        with self.assertRaises(UserError):
            self.as_tester(self.tester).action_claim_testing_task()
