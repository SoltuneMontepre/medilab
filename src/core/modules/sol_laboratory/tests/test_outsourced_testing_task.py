from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOutsourcedTestingTask(DispatchCase):
    """The lead test is assigned to the tester when its head of department outsources it."""

    def my_open_tasks(self):
        return self.as_person(self.env[MODEL_TASK], self.tester).search(
            [("is_mine", "=", True), ("status", "in", ("assigned", "in_progress"))]
        )

    def test_outsourcing_a_test_ends_its_testing_task_and_keeps_its_department(self):
        self.outsource()

        self.assertEqual(self.task.status, "cancelled")
        self.assertNotIn(self.task, self.my_open_tasks())
        self.assertEqual(self.test._tested_by(), self.department)

    def test_outsourcing_a_test_straight_away_ends_its_testing_task(self):
        self.test.outsourcing_suggested = False

        self.as_person(self.test, self.head)._outsource_now(self.northern_way, "The AAS is under repair.")

        self.assertEqual(self.task.status, "cancelled")

    def test_moving_a_test_to_another_subcontractor_leaves_it_without_an_open_testing_task(self):
        self.as_person(self.outsource(), self.head).action_cancel()
        reopened = self.testing_task(self.test, self.tester)

        self.as_person(self.test, self.head)._move_to_subcontractor(self.southern_way)

        self.assertEqual(reopened.status, "cancelled")

    def test_the_testing_task_of_an_outsourced_test_cannot_be_started(self):
        self.outsource()
        task = self.testing_task(self.test, self.tester)
        mine = self.as_person(task, self.tester)

        self.assertFalse(mine.can_start)
        self.assertFalse(mine._mobile_actions()["start"])
        with self.assertRaises(UserError):
            mine.action_start()
        self.assertEqual(task.status, "assigned")

    def test_the_testing_task_of_a_test_in_the_laboratory_can_still_be_started(self):
        mine = self.as_person(self.task, self.tester)

        self.assertTrue(mine.can_start)
        self.assertTrue(mine._mobile_actions()["start"])
        mine.action_start()
        self.assertEqual(self.task.status, "in_progress")

    def test_a_rejected_subcontractor_result_opens_no_testing_task(self):
        result = self.enter_on_portal(self.receive_dispatch(self.outsource()), "0.008")
        self.send_portal_result(result)

        self.as_person(result, self.head).action_reject("The blank was contaminated.")

        self.assertEqual(self.test.status, "outsourced")
        self.assertFalse(self.test._testing_task())
