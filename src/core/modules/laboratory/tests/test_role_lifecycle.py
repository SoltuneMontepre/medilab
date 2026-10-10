from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.laboratory.constants.models import MODEL_PERMISSION, MODEL_ROLE, MODEL_TEST_PARAMETER


@tagged("post_install", "-at_install")
class TestRoleLifecycle(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.read, cls.delete = cls.env[MODEL_PERMISSION].create(
            [
                {"name": "Read parameters", "document_model": MODEL_TEST_PARAMETER, "action": "read"},
                {"name": "Delete parameters", "document_model": MODEL_TEST_PARAMETER, "action": "delete"},
            ]
        )
        cls.role = cls.env[MODEL_ROLE].create(
            {"code": "qa_tester", "name": "Tester", "permission_ids": [Command.set(cls.read.ids)]}
        )

    def test_role_generates_its_group(self):
        group = self.env.ref("laboratory.group_role_qa_tester")

        self.assertEqual(self.role.group_id, group)
        self.assertEqual(group.name, "Role: qa_tester")
        data = self.env["ir.model.data"].search([("module", "=", "laboratory"), ("name", "=", "group_role_qa_tester")])
        self.assertTrue(data.noupdate)

    def test_role_group_implies_exactly_its_permission_groups(self):
        export = self.env.ref("base.group_allow_export")
        self.role.group_id.implied_ids = [Command.link(export.id)]

        self.role.permission_ids = [Command.set(self.delete.ids)]

        implied = self.role.group_id.implied_ids
        self.assertEqual(implied & (self.read | self.delete).group_id, self.delete.group_id)
        self.assertIn(export, implied)

    def test_holder_of_the_role_holds_its_permissions(self):
        user = new_test_user(self.env, login="role.holder", groups="base.group_user,laboratory.group_role_qa_tester")

        self.assertIn(self.read.group_id, user.all_group_ids)
        self.role.permission_ids = [Command.link(self.delete.id)]
        self.assertIn(self.delete.group_id, user.all_group_ids)
        self.role.permission_ids = [Command.unlink(self.read.id)]
        self.assertNotIn(self.read.group_id, user.all_group_ids)

    def test_role_cannot_be_archived(self):
        self.assertNotIn("active", self.env[MODEL_ROLE]._fields)

    def test_deleting_a_role_deletes_its_group(self):
        group = self.role.group_id

        self.role.unlink()

        self.assertFalse(group.exists())

    def test_role_code_is_lowercase_letters_digits_and_underscores(self):
        for code in ("Tester", "head-of-sales", "1st_line", ""):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                self.env[MODEL_ROLE].create({"code": code, "name": "Role"})

    def test_role_code_is_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_ROLE].create({"code": "qa_tester", "name": "Tester again"})

    def test_role_code_cannot_change(self):
        with self.assertRaises(UserError):
            self.role.code = "lab_tester"

        self.role.name = "Laboratory tester"
        self.assertEqual(self.role.name, "Laboratory tester")
