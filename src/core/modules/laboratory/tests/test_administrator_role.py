from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.laboratory.constants.models import MODEL_PERMISSION, MODEL_PERMISSION_MIXIN, MODEL_TEST_PARAMETER

REQUIRED_ACTIONS = ("read", "create", "edit", "delete")


@tagged("post_install", "-at_install")
class TestAdministratorRole(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.env.ref("laboratory.role_administrator")

    def test_administrator_role_holds_every_permission(self):
        self.assertEqual(self.administrator.permission_ids, self.env[MODEL_PERMISSION].search([]))

    def test_administrator_holds_a_permission_added_later(self):
        user = new_test_user(
            self.env, login="administrator", groups="base.group_user,laboratory.group_role_administrator"
        )

        permission = self.env[MODEL_PERMISSION].create(
            {"name": "Sign parameters", "document_model": MODEL_TEST_PARAMETER, "action": "sign"}
        )

        self.assertIn(permission, self.administrator.permission_ids)
        self.assertIn(permission.group_id, user.all_group_ids)

    def test_administrator_also_configures_odoo(self):
        self.assertIn(self.env.ref("base.group_system"), self.administrator.group_id.implied_ids)

    def test_administrator_role_cannot_be_deleted_renamed_or_stripped(self):
        refused = (
            self.administrator.unlink,
            lambda: self.administrator.write({"name": "Super user"}),
            lambda: self.administrator.write({"code": "admin"}),
            lambda: self.administrator.write(
                {"permission_ids": [Command.unlink(self.administrator.permission_ids[0].id)]}
            ),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises(UserError):
                action()
        self.assertTrue(self.administrator.exists())

    def test_every_document_type_has_a_permission_for_each_action(self):
        # A document type without a permission for an action would lock out even the administrator.
        for model_name in self.env.registry[MODEL_PERMISSION_MIXIN]._inherit_children:
            model = self.env[model_name]
            if model._abstract:
                continue
            actions = {*REQUIRED_ACTIONS, "archive"} if "active" in model._fields else set(REQUIRED_ACTIONS)
            shipped = self.env[MODEL_PERMISSION].search([("document_model", "=", model_name), ("scope", "=", "all")])
            with self.subTest(model=model_name):
                self.assertFalse(actions - set(shipped.mapped("action")))
