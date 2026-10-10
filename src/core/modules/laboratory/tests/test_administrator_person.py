from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAdministratorPerson(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.person = cls.env.ref("laboratory.person_administrator")
        cls.role = cls.env.ref("laboratory.role_administrator")

    def test_default_administrator_holds_the_administrator_role(self):
        user = self.env.ref("base.user_admin")

        self.assertEqual(self.person.user_id, user)
        self.assertIn(self.role, self.person.role_ids)
        self.assertIn(self.role.group_id, user.group_ids)

    def test_administrator_person_cannot_be_archived_deleted_or_lose_the_role(self):
        for action in (
            self.person.action_archive,
            self.person.unlink,
            lambda: self.person.write({"role_ids": [Command.unlink(self.role.id)]}),
            lambda: self.person.write({"user_id": False}),
        ):
            with self.subTest(action=action), self.assertRaises(UserError):
                action()
        self.assertTrue(self.person.active)
