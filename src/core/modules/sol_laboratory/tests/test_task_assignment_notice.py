from odoo.tests import tagged

from .task_case import TaskCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_MESSAGE, MODEL_TASK, MODEL_TASK_REASSIGN

ASSIGNED_EVENT = "sol_laboratory.event_task_assigned"


@tagged("post_install", "-at_install")
class TestTaskAssignmentNotice(TaskCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head = cls.create_person(
            "Do Thi Giang",
            cls.chemistry,
            "giang.do",
            permissions=[
                "task.read.own_department",
                "task.create.own_department",
                "task.edit.own_department",
                "person.read.own_department",
            ],
        )
        cls.colleague = cls.create_person("Pham Thi Dung", cls.chemistry, "dung.pham")
        for person in cls.chemist | cls.colleague | cls.head:
            person.user_id.partner_id.email = f"{person.user_id.login}@anphu.example"

    def assign(self, task, assignee, **vals):
        wizard = self.as_person(self.env[MODEL_TASK_REASSIGN], self.head).with_context(active_ids=task.ids)
        wizard.create({"department_id": self.chemistry.id, "assignee_id": assignee.id, **vals}).action_confirm()

    def notices(self, task):
        """The messages telling a person that the task was assigned to them."""
        return self.env[MODEL_MAIL_MESSAGE].search(
            [
                ("model", "=", MODEL_TASK),
                ("res_id", "=", task.id),
                ("subtype_id", "=", self.env.ref(ASSIGNED_EVENT).id),
            ]
        )

    def told(self, task):
        """The partners told that the task was assigned to them."""
        return self.notices(task).notification_ids.res_partner_id

    def test_assigning_a_task_tells_the_assignee_who_assigned_it(self):
        task = self.receive_sample(self.chemistry)
        self.assertFalse(self.told(task))

        self.assign(task, self.chemist)

        self.assertEqual(self.told(task), self.chemist.user_id.partner_id)
        self.assertIn(self.head.name, self.notices(task).body or "")

    def test_claiming_a_task_tells_nobody(self):
        task = self.receive_sample(self.chemistry)

        self.as_person(task, self.chemist).action_claim()

        self.assertEqual(task.assignee_id, self.chemist)
        self.assertFalse(self.told(task))

    def test_assigning_a_task_to_oneself_tells_nobody(self):
        task = self.receive_sample(self.chemistry)

        self.assign(task, self.head)

        self.assertEqual(task.assignee_id, self.head)
        self.assertFalse(self.told(task))

    def test_moving_a_task_to_another_person_tells_only_the_new_assignee(self):
        task = self.receive_sample(self.chemistry)
        self.assign(task, self.chemist)

        self.assign(task, self.colleague, reason="The chemist is on leave")

        self.assertEqual(self.told(task), self.chemist.user_id.partner_id | self.colleague.user_id.partner_id)
        self.assertEqual(task.assignee_id, self.colleague)

    def test_reassigning_a_task_to_the_same_person_does_not_create_another_open_notice(self):
        task = self.receive_sample(self.chemistry)
        self.assign(task, self.chemist)
        self.assign(task, self.colleague, reason="The chemist is on leave")
        self.assign(task, self.chemist, reason="The chemist is back")

        open_notices = self.notices(task).notification_ids.filtered(
            lambda notice: notice.res_partner_id == self.chemist.user_id.partner_id and not notice.is_read
        )
        self.assertEqual(len(open_notices), 1)

    def test_a_task_a_person_creates_for_someone_else_tells_the_assignee(self):
        task = self.as_person(self.env[MODEL_TASK], self.head).create(
            {
                "type_id": self.general.id,
                "name": "Call the customer",
                "assignee_id": self.chemist.id,
                "department_id": self.chemistry.id,
                "deadline": self.tomorrow,
            }
        )

        self.assertEqual(self.told(task), self.chemist.user_id.partner_id)

    def test_a_task_nobody_assigned_by_hand_tells_nobody(self):
        task = self.create_by_hand(self.chemist, department_id=self.chemistry.id)

        self.assertFalse(self.told(task))
