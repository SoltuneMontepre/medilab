from psycopg2 import IntegrityError

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PERMISSION,
    MODEL_PERSON,
    MODEL_ROLE,
    MODEL_TEST_PARAMETER,
)

OPERATION_FLAGS = ("perm_read", "perm_write", "perm_create", "perm_unlink")


@tagged("post_install", "-at_install")
class TestPermissionGeneration(TransactionCase):
    def create_permission(self, action, scope="all", document_model=MODEL_TEST_PARAMETER):
        return self.env[MODEL_PERMISSION].create(
            {"name": f"{action} records", "document_model": document_model, "action": action, "scope": scope}
        )

    def generated(self, kind, code):
        return self.env.ref(f"laboratory.{kind}_permission_{code.replace('.', '_')}", raise_if_not_found=False)

    def test_permission_generates_its_group_access_rule_and_record_rule(self):
        permission = self.create_permission("delete")

        self.assertEqual(permission.code, "test.parameter.delete.all")
        self.assertEqual(self.generated("group", permission.code), permission.group_id)
        access = self.generated("access", permission.code)
        rule = self.generated("rule", permission.code)
        self.assertEqual((access.model_id.model, access.group_id), (MODEL_TEST_PARAMETER, permission.group_id))
        self.assertEqual((rule.model_id.model, rule.groups), (MODEL_TEST_PARAMETER, permission.group_id))
        self.assertEqual(rule.domain_force, "[(1, '=', 1)]")
        generated_data = self.env["ir.model.data"].search(
            [("module", "=", "laboratory"), ("name", "like", "%_permission_test_parameter_delete_all")]
        )
        self.assertEqual(len(generated_data), 3)
        self.assertTrue(all(generated_data.mapped("noupdate")))

    def test_each_action_maps_to_its_operation(self):
        expected = {
            "read": "perm_read",
            "create": "perm_create",
            "edit": "perm_write",
            "archive": "perm_write",
            "delete": "perm_unlink",
        }
        for action, flag in expected.items():
            permission = self.env[MODEL_PERMISSION].new(
                {"document_model": MODEL_DEPARTMENT, "action": action, "scope": "all"}
            )
            for kind, values in (("access", permission._access_values()), ("rule", permission._rule_values())):
                with self.subTest(action=action, kind=kind):
                    self.assertEqual([name for name in OPERATION_FLAGS if values.get(name)], [flag])

    def test_sign_permission_generates_only_its_group(self):
        permission = self.create_permission("sign")

        self.assertEqual(self.generated("group", permission.code), permission.group_id)
        self.assertIsNone(self.generated("access", permission.code))
        self.assertIsNone(self.generated("rule", permission.code))

    def test_administrator_holds_every_new_permission(self):
        permission = self.create_permission("read")

        self.assertIn(permission.group_id, self.env.ref("laboratory.group_role_administrator").implied_ids)

    def test_permission_holder_without_odoo_settings_creates_permissions(self):
        user = new_test_user(
            self.env,
            login="permission.manager",
            groups="base.group_user,laboratory.group_permission_permission_read_all,"
            "laboratory.group_permission_permission_create_all",
        )

        permission = (
            self.env[MODEL_PERMISSION]
            .with_user(user)
            .create({"name": "Read parameters", "document_model": MODEL_TEST_PARAMETER, "action": "read"})
        )

        self.assertTrue(self.generated("rule", permission.code))

    def test_document_type_action_and_scope_cannot_change(self):
        permission = self.create_permission("read")

        for vals in ({"action": "create"}, {"document_model": MODEL_PERMISSION}, {"scope": "own_department"}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                permission.write(vals)
        permission.write({"name": "Read test parameters", "action": "read"})
        self.assertEqual(permission.name, "Read test parameters")

    def test_same_action_on_same_document_type_and_scope_is_refused(self):
        self.create_permission("read")

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_permission("read")

    def test_own_department_needs_a_department_on_the_document_type(self):
        with self.assertRaises(ValidationError):
            self.create_permission("read", scope="own_department")

    def test_edit_and_archive_need_a_document_type_that_tells_them_apart(self):
        for action in ("edit", "archive"):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                self.create_permission(action)

    def test_archive_needs_a_document_type_that_can_be_archived(self):
        with self.assertRaises(ValidationError):
            self.create_permission("archive", document_model=MODEL_ROLE)

    def test_own_department_rule_limits_records_to_the_users_department(self):
        permission = self.env[MODEL_PERMISSION].new(
            {"document_model": MODEL_PERSON, "action": "read", "scope": "own_department"}
        )

        self.assertEqual(
            permission._rule_values()["domain_force"],
            "[('department_id.person_ids', 'any', [('user_id', '=', user.id), ('active', '=', True)])]",
        )

    def test_deleting_a_permission_deletes_what_it_generated(self):
        permission = self.create_permission("delete")
        group, access, rule = (self.generated(kind, permission.code) for kind in ("group", "access", "rule"))

        permission.unlink()

        self.assertFalse(group.exists() or access.exists() or rule.exists())

    def test_permission_whose_group_another_rule_uses_cannot_be_deleted(self):
        permission = self.create_permission("read")
        shared = self.env["ir.rule"].create(
            {
                "name": "Shared parameter rule",
                "model_id": self.env["ir.model"]._get(MODEL_TEST_PARAMETER).id,
                "groups": [Command.set([permission.group_id.id, self.env.ref("base.group_user").id])],
                "domain_force": "[(1, '=', 1)]",
            }
        )

        with self.assertRaises(UserError) as refusal:
            permission.unlink()

        self.assertIn("Shared parameter rule", str(refusal.exception))
        self.assertTrue(shared.exists() and permission.exists())

    def test_holders_are_set_from_the_role_or_the_person(self):
        permission = self.create_permission("read")
        role = self.env[MODEL_ROLE].create({"code": "qa_reader", "name": "Reader"})

        for action in (
            lambda: permission.write({"role_ids": [Command.link(role.id)]}),
            lambda: role.write({"person_ids": [Command.clear()]}),
        ):
            with self.subTest(action=action), self.assertRaises(UserError):
                action()

    def test_permission_shipped_with_a_module_cannot_be_deleted(self):
        with self.assertRaises(UserError):
            self.env.ref("laboratory.permission_permission_read_all").unlink()

    def test_document_types_are_medilab_models(self):
        document_types = [name for name, _label in self.env[MODEL_PERMISSION]._selection_document_model()]

        self.assertIn(MODEL_TEST_PARAMETER, document_types)
        self.assertTrue(all(name.startswith("medilab.") for name in document_types))
