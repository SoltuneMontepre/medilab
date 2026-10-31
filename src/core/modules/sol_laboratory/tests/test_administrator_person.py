from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestAdministratorPerson(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person = cls.env.ref("sol_laboratory.person_administrator")
        cls.role = cls.env.ref("sol_laboratory.role_administrator")

    def test_default_administrator_holds_the_administrator_role(self):
        user = self.env.ref("base.user_admin")

        self.assertEqual(self.person.user_id, user)
        self.assertEqual(self.person.employee_id, user.employee_id)
        self.assertIn(self.role, self.person.role_ids)
        self.assertIn(self.role.group_id, user.group_ids)

    def test_administrator_person_cannot_be_archived_deleted_or_lose_the_role(self):
        for action in (
            self.person.action_archive,
            self.person.unlink,
            lambda: self.person.write({"role_ids": [Command.unlink(persisted_id(self.role))]}),
            lambda: self.person.write({"user_id": False}),
            lambda: self.person.employee_id.write({"user_id": False}),
            self.person.employee_id.action_archive,
            self.person.employee_id.unlink,
        ):
            with self.subTest(action=action), self.assertRaises(UserError):
                action()
        self.assertTrue(self.person.active)
