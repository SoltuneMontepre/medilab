from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .task_case import TaskCase


@tagged("post_install", "-at_install")
class TestTaskLifecycle(TaskCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.creator = cls.create_person("Le Van Cuong", cls.chemistry, "cuong.le", permissions=["task.create.all"])

    def hand_task_vals(self, **vals):
        return {
            "type_id": self.general.id,
            "name": "Call the customer",
            "assignee_id": self.chemist.id,
            "deadline": self.tomorrow,
            **vals,
        }

    def test_system_task_is_done_when_its_work_is_done(self):
        task = self.receive_sample(self.chemistry)
        self.as_person(task, self.chemist).action_claim()

        self.tasks._close_for_document(self.chemistry, "enter_result")
        self.assertEqual(task.status, "done")
        self.assertTrue(task.done_at)

    def test_assignee_cannot_mark_a_system_task_done(self):
        task = self.receive_sample(self.chemistry)
        self.as_person(task, self.chemist).action_claim()

        with self.assertRaises(UserError):
            self.as_person(task, self.chemist).action_done()
        self.assertEqual(task.status, "assigned")

    def test_closing_leaves_tasks_of_other_actions_and_hand_tasks_open(self):
        task = self.receive_sample(self.chemistry)
        by_hand = self.create_by_hand(
            self.chemist, document_model="medilab.department", document_id=self.chemistry.id, action="enter_result"
        )

        self.tasks._close_for_document(self.chemistry, "sign")
        self.assertEqual(task.status, "open")
        self.tasks._close_for_document(self.chemistry)
        self.assertEqual((task.status, by_hand.status), ("done", "assigned"))

    def test_system_task_is_cancelled_with_its_work(self):
        task = self.receive_sample(self.chemistry)

        self.tasks._cancel_for_document(self.chemistry)
        self.assertEqual(task.status, "cancelled")

    def test_assignee_starts_and_marks_a_hand_task_done(self):
        task = self.create_by_hand(self.chemist)

        self.as_person(task, self.chemist).action_start()
        self.assertEqual(task.status, "in_progress")
        self.as_person(task, self.chemist).action_done()
        self.assertEqual(task.status, "done")

    def test_only_the_assignee_marks_a_hand_task_done(self):
        task = self.create_by_hand(self.chemist)

        with self.assertRaises(UserError):
            self.as_person(task, self.microbiologist).action_done()
        self.assertEqual(task.status, "assigned")

    def test_hand_task_needs_an_assignee_and_a_deadline(self):
        tasks = self.as_person(self.tasks, self.creator)

        for vals in ({"assignee_id": False}, {"deadline": False}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                tasks.create(self.hand_task_vals(**vals))
        task = tasks.create(self.hand_task_vals())
        self.assertEqual((task.status, task.sudo().assigned_by_id), ("assigned", self.creator))

    def test_tasks_of_an_event_type_are_not_created_by_hand(self):
        with self.assertRaises(UserError):
            self.as_person(self.tasks, self.creator).create(self.hand_task_vals(type_id=self.testing.id))

    def test_creating_a_task_by_hand_needs_the_create_permission(self):
        with self.assertRaises(AccessError):
            self.as_person(self.tasks, self.chemist).create(self.hand_task_vals())

    def test_event_task_gets_the_default_deadline_of_its_type(self):
        task = self.receive_sample(self.chemistry)

        self.assertAlmostEqual((task.deadline - task.create_date).total_seconds(), 48 * 3600, delta=60)

    def test_department_with_an_unfinished_task_cannot_be_archived_or_deleted(self):
        self.receive_sample(self.microbiology)

        with self.assertRaises(UserError):
            self.microbiology.action_archive()
        with self.assertRaises(UserError):
            self.microbiology.unlink()

    def test_hand_task_assignee_belongs_to_its_department(self):
        with self.assertRaises(UserError):
            self.as_person(self.tasks, self.creator).create(
                self.hand_task_vals(assignee_id=self.microbiologist.id, department_id=self.chemistry.id)
            )
