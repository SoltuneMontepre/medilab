from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .task_case import TaskCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK_REASSIGN


@tagged("post_install", "-at_install")
class TestTaskReassigning(TaskCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head = cls.create_person(
            "Do Thi Giang",
            cls.chemistry,
            "giang.do",
            permissions=["task.read.own_department", "task.edit.own_department", "person.read.own_department"],
        )
        cls.colleague = cls.create_person("Pham Thi Dung", cls.chemistry, "dung.pham")

    def assign(self, tasks, **vals):
        wizard = self.as_person(self.env[MODEL_TASK_REASSIGN], self.head).with_context(active_ids=tasks.ids)
        return wizard.create(vals).action_confirm()

    def test_head_assigns_a_queued_task_without_a_reason(self):
        task = self.receive_sample(self.chemistry)

        self.assign(task, department_id=self.chemistry.id, assignee_id=self.chemist.id)
        self.assertEqual((task.assignee_id, task.assigned_by_id, task.status), (self.chemist, self.head, "assigned"))
        self.assertFalse(task.reassign_reason)

    def test_head_assigns_several_tasks_at_once(self):
        tasks = self.receive_sample(self.chemistry) | self.receive_sample(self.chemistry)

        self.assign(tasks, department_id=self.chemistry.id, assignee_id=self.chemist.id)
        self.assertEqual(tasks.assignee_id, self.chemist)

    def test_reassigning_without_a_reason_is_refused(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)

        with self.assertRaises(UserError):
            self.assign(task, department_id=self.chemistry.id, assignee_id=self.colleague.id)
        with self.assertRaises(UserError):
            self.as_person(task, self.head).write({"assignee_id": self.colleague.id})
        self.assertEqual(task.assignee_id, self.chemist)

    def test_reason_is_kept_on_the_reassigned_task(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)

        self.assign(task, department_id=self.chemistry.id, assignee_id=self.colleague.id, reason="An is on leave")
        self.assertEqual((task.assignee_id, task.reassign_reason), (self.colleague, "An is on leave"))

    def test_moving_to_another_department_needs_a_reason(self):
        task = self.receive_sample(self.chemistry)

        with self.assertRaises(UserError):
            self.assign(task, department_id=self.microbiology.id)
        self.assign(task, department_id=self.microbiology.id, reason="Needs a culture")
        self.assertEqual((task.department_id, task.status), (self.microbiology, "open"))

    def test_assignee_must_belong_to_the_department(self):
        task = self.receive_sample(self.chemistry)

        with self.assertRaises(UserError):
            self.assign(task, department_id=self.chemistry.id, assignee_id=self.microbiologist.id)

    def test_head_cannot_assign_tasks_of_another_department(self):
        task = self.receive_sample(self.microbiology)

        with self.assertRaises(AccessError):
            self.as_person(task, self.head).write({"assignee_id": self.microbiologist.id})

    def test_person_without_the_edit_permission_cannot_assign(self):
        task = self.receive_sample(self.chemistry)

        with self.assertRaises(AccessError):
            self.as_person(task, self.chemist).write({"assignee_id": self.colleague.id})

    def test_confirming_without_a_change_keeps_the_task_as_it_is(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)
        self.as_person(task, self.chemist).action_start()

        self.assign(task, department_id=self.chemistry.id, assignee_id=self.chemist.id)
        self.assertEqual(task.status, "in_progress")
