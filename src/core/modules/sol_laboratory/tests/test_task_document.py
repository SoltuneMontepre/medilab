from odoo.tests import tagged

from .task_case import TaskCase


@tagged("post_install", "-at_install")
class TestTaskDocument(TaskCase):
    def test_clicking_a_task_opens_its_document_at_its_action(self):
        task = self.receive_sample(self.chemistry)

        action = task.action_open_document()
        self.assertEqual((action["res_model"], action["res_id"]), ("medilab.department", self.chemistry.id))
        self.assertEqual(action["context"]["medilab_task_action"], "enter_result")

    def test_task_without_a_document_opens_itself(self):
        task = self.create_by_hand(self.chemist)

        action = task.action_open_document()
        self.assertEqual((action["res_model"], action["res_id"]), ("medilab.task", task.id))
