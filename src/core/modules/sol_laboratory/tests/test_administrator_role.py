from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_PERMISSION_MIXIN, MODEL_TEST_PARAMETER
from odoo.addons.sol_laboratory.services.model_lookup import model_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestAdministratorRole(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.administrator = cls.env.ref("sol_laboratory.role_administrator")

    def test_administrator_role_holds_every_permission(self):
        self.assertEqual(self.administrator.permission_ids, self.env[MODEL_PERMISSION].search([]))

    def test_administrator_holds_a_permission_added_later(self):
        user = new_test_user(
            self.env, login="administrator", groups="base.group_user,sol_laboratory.group_role_administrator"
        )

        parameters = type(self.env[MODEL_TEST_PARAMETER])
        # Test parameters are never signed, so no module ships the permission this test adds.
        self.patch(parameters, "_permission_actions", (*parameters._permission_actions, "sign"))
        permission = self.env[MODEL_PERMISSION].create(
            {"name": "Sign parameters", "document_model": MODEL_TEST_PARAMETER, "action": "sign"}
        )

        self.assertIn(permission, self.administrator.permission_ids)
        self.assertIn(permission.group_id, user.all_group_ids)

    def test_administrator_also_configures_odoo_and_manages_its_employees(self):
        implied = self.administrator.group_id.implied_ids

        self.assertTrue(self.env.ref("base.group_system") | self.env.ref("hr.group_hr_manager") <= implied)

    def test_administrator_role_cannot_be_deleted_renamed_or_stripped(self):
        refused = (
            self.administrator.unlink,
            lambda: self.administrator.write({"name": "Super user"}),
            lambda: self.administrator.write({"code": "admin"}),
            lambda: self.administrator.write(
                {"permission_ids": [Command.unlink(persisted_id(self.administrator.permission_ids[0]))]}
            ),
        )
        for action in refused:
            with self.subTest(action=action), self.assertRaises(UserError):
                action()
        self.assertTrue(self.administrator.exists())

    def test_every_document_type_has_a_permission_for_each_action(self):
        # A document type without a permission for an action would lock out even the administrator.
        for model_name in self.env.registry[MODEL_PERMISSION_MIXIN]._inherit_children:
            model = model_as(self.env, model_name, self.env[MODEL_PERMISSION_MIXIN])
            if model._abstract:
                continue
            actions = set(model._supported_permission_actions())
            shipped = self.env[MODEL_PERMISSION].search([("document_model", "=", model_name), ("scope", "=", "all")])
            with self.subTest(model=model_name):
                self.assertFalse(actions - set(shipped.mapped("action")))

    def test_no_permission_names_an_action_its_document_type_does_not_have(self):
        # Such as deleting ways of testing, which are archived, never deleted.
        for permission in self.env[MODEL_PERMISSION].search([]):
            with self.subTest(permission=permission.code):
                self.assertIn(
                    permission.action,
                    model_as(
                        self.env, permission.document_model, self.env[MODEL_PERMISSION_MIXIN]
                    )._supported_permission_actions(),
                )
