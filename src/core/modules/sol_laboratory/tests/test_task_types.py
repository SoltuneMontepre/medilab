from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .task_case import TaskCase


@tagged("post_install", "-at_install")
class TestTaskTypes(TaskCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.env.ref("base.user_admin")

    def route_to_signers(self):
        self.testing.with_user(self.administrator).write({"route": "role", "role_id": self.signer_role.id})

    def test_task_type_cannot_be_created_or_deleted_from_the_screen(self):
        task_types = self.testing.with_user(self.administrator)

        with self.assertRaises(AccessError):
            task_types.create({"code": "stock_take", "name": "Stock take", "route": "department"})
        with self.assertRaises(AccessError):
            task_types.unlink()

    def test_only_route_role_and_default_deadline_change(self):
        task_type = self.testing.with_user(self.administrator)

        task_type.write({"deadline_hours": 24})
        self.route_to_signers()
        for vals in ({"name": "Testing"}, {"trigger": "manual"}, {"action": "sign"}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                task_type.write(vals)

    def test_new_tasks_follow_the_route_the_administrator_chose(self):
        self.route_to_signers()

        task = self.receive_sample(self.chemistry)
        self.assertFalse(task.department_id)
        self.assertEqual(task.type_id.role_id, self.signer_role)

    def test_existing_tasks_keep_their_queue_when_the_route_changes(self):
        task = self.receive_sample(self.chemistry)

        self.route_to_signers()
        self.assertEqual(task.department_id, self.chemistry)

    def test_role_routed_type_needs_its_role(self):
        with self.assertRaises(UserError):
            self.testing.with_user(self.administrator).write({"route": "role"})

    def test_trigger_creates_a_task_of_each_of_its_types(self):
        self.assertEqual(self.receive_sample(self.chemistry).type_id, self.testing)
        self.assertFalse(self.tasks._create_for_event("nothing_happened"))

    def test_routing_away_from_a_role_clears_the_role(self):
        self.route_to_signers()

        self.testing.with_user(self.administrator).write({"route": "department"})
        self.assertFalse(self.testing.role_id)
