from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged

from .task_case import TaskCase
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK_REASSIGN
from odoo.addons.sol_laboratory.services.record_id import persisted_id


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

    def test_whitespace_is_not_a_reason_for_reassignment_through_the_wizard(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)
        fields = ["assignee_id", "department_id", "status", "reassign_reason", "assigned_by_id", "write_date"]
        before = task.read(fields)
        for reason in ("   ", "\n\t"):
            with self.subTest(reason=repr(reason)):
                with self.assertRaisesRegex(UserError, "Give a reason for moving"), self.env.cr.savepoint():
                    self.assign(task, department_id=self.chemistry.id, assignee_id=self.colleague.id, reason=reason)
                self.assertEqual(task.read(fields), before)
        self.assign(task, department_id=self.chemistry.id, assignee_id=self.colleague.id, reason="An is on leave")
        self.assertEqual((task.assignee_id, task.reassign_reason), (self.colleague, "An is on leave"))

    def test_whitespace_is_not_a_reason_for_a_direct_reassignment(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)
        fields = ["assignee_id", "department_id", "status", "reassign_reason", "assigned_by_id", "write_date"]
        before = task.read(fields)
        for reason in ("   ", "\n\t"):
            with self.subTest(reason=repr(reason)):
                with self.assertRaisesRegex(UserError, "Give a reason for moving"), self.env.cr.savepoint():
                    self.as_person(task, self.head).write({"assignee_id": self.colleague.id, "reassign_reason": reason})
                self.assertEqual(task.read(fields), before)
        self.as_person(task, self.head).write({"assignee_id": self.colleague.id, "reassign_reason": "An is on leave"})
        self.assertEqual((task.assignee_id, task.reassign_reason), (self.colleague, "An is on leave"))

    def test_moving_to_another_department_needs_a_reason(self):
        task = self.receive_sample(self.chemistry)

        with self.assertRaises(UserError):
            self.assign(task, department_id=self.microbiology.id)
        self.assign(task, department_id=self.microbiology.id, reason="Needs a culture")
        self.assertEqual((task.department_id, task.status), (self.microbiology, "open"))

    def test_head_who_moved_a_task_to_another_department_still_reads_it_but_cannot_change_it(self):
        task = self.receive_sample(self.chemistry)

        self.assign(task, department_id=self.microbiology.id, reason="Needs a culture")

        moved = self.as_person(task, self.head)
        self.assertEqual(moved.read(["department_id", "can_edit"])[0]["department_id"][0], self.microbiology.id)
        self.assertFalse(moved.can_edit)
        with self.assertRaises(AccessError):
            moved.write({"note": "Back to chemistry"})
        self.assertFalse(self.as_person(task, self.colleague).has_access("read"))

    def test_nobody_records_a_mover_by_hand(self):
        task = self.receive_sample(self.chemistry)

        with self.assertRaisesRegex(UserError, "Only the system records who moved"):
            self.as_person(task, self.head).write({"moved_out_by_ids": [Command.link(persisted_id(self.colleague))]})
        self.assertFalse(task.moved_out_by_ids)

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
