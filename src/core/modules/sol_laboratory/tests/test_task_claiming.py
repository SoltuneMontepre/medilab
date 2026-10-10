from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .task_case import SIGNATURE_REQUESTED, TaskCase


@tagged("post_install", "-at_install")
class TestTaskClaiming(TaskCase):
    def test_event_task_waits_in_the_department_queue(self):
        task = self.receive_sample(self.chemistry)

        self.assertEqual((task.type_id, task.department_id, task.status), (self.testing, self.chemistry, "open"))
        self.assertFalse(task.assignee_id)
        queue = self.as_person(self.tasks, self.chemist).search([("in_my_queue", "=", True)])
        self.assertEqual(queue, task)

    def test_person_claims_an_unassigned_task_of_their_department(self):
        task = self.receive_sample(self.chemistry)

        self.as_person(task, self.chemist).action_claim()
        self.assertEqual((task.assignee_id, task.assigned_by_id, task.status), (self.chemist, self.chemist, "assigned"))

    def test_task_of_another_department_cannot_be_claimed(self):
        task = self.receive_sample(self.chemistry)

        self.assertFalse(self.as_person(self.tasks, self.microbiologist).search([("id", "=", task.id)]))
        with self.assertRaises(UserError):
            self.as_person(task, self.microbiologist).action_claim()
        self.assertFalse(task.assignee_id)

    def test_claimed_task_cannot_be_claimed_again(self):
        colleague = self.create_person("Pham Thi Dung", self.chemistry, "dung.pham")
        task = self.receive_sample(self.chemistry)
        self.as_person(task, self.chemist).action_claim()

        with self.assertRaises(UserError):
            self.as_person(task, colleague).action_claim()
        self.assertEqual(task.assignee_id, self.chemist)

    def test_task_locked_by_a_concurrent_claim_is_told_it_is_claimed(self):
        task = self.receive_sample(self.chemistry)
        self.patch(type(task), "try_lock_for_update", lambda records, **kwargs: records.browse())

        with self.assertRaises(UserError):
            self.as_person(task, self.chemist).action_claim()

    def test_holders_of_the_role_claim_a_role_routed_task(self):
        self.chemist.role_ids = [Command.link(self.signer_role.id)]
        task = self.tasks._create_for_event(SIGNATURE_REQUESTED, self.chemistry, department=self.chemistry)

        self.assertFalse(task.department_id)
        with self.assertRaises(UserError):
            self.as_person(task, self.microbiologist).action_claim()
        self.as_person(task, self.chemist).action_claim()
        self.assertEqual(task.assignee_id, self.chemist)

    def test_holders_of_the_role_see_its_queue(self):
        self.chemist.role_ids = [Command.link(self.signer_role.id)]
        task = self.tasks._create_for_event(SIGNATURE_REQUESTED, self.chemistry)

        self.assertIn(task, self.as_person(self.tasks, self.chemist).search([]))
        self.assertNotIn(task, self.as_person(self.tasks, self.microbiologist).search([]))
