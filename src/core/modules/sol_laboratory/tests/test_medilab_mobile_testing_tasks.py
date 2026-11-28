from freezegun import freeze_time

from odoo.tests import tagged

from .laboratory_files_case import PASSWORD
from .mobile_phones import PhoneCalls
from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.medilab_mobile import ACTION_REFUSED


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestMedilabMobileTestingTasks(SchedulingCase, PhoneCalls):
    """The head assigns the lead testing task of the received sample on Medilab Mobile; a microbiologist is also
    authorized to test lead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head.user_id.password = PASSWORD
        cls.authorize(cls.microbiologist, cls.parameter)
        cls.task = cls.testing_task(cls.test)

    def test_a_testing_task_is_not_moved_to_another_department_on_the_phone(self):
        path = f"/tasks/{self.task.id}/assign"

        self.assertApiRefused(
            ACTION_REFUSED,
            self.on_phone(self.head, "POST", path, {"department_id": self.microbiology.id, "reason": "Culture"}),
        )
        self.assertApiRefused(
            ACTION_REFUSED,
            self.on_phone(self.head, "POST", path, {"assignee_id": self.microbiologist.id, "reason": "Culture"}),
        )
        self.assertEqual(self.task.department_id, self.department)
        self.assertFalse(self.task.assignee_id)

    def test_the_head_assigns_a_testing_task_to_a_tester_of_its_department_on_the_phone(self):
        response = self.on_phone(self.head, "POST", f"/tasks/{self.task.id}/assign", {"assignee_id": self.tester.id})

        self.answered(response)
        self.assertEqual((self.task.department_id, self.task.assignee_id), (self.department, self.tester))
