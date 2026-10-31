from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .common import MasterDataCase
from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_RES_GROUPS, MODEL_TESTING_METHOD_STEP
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.services.record_id import persisted_id

STEP_PERMISSIONS = ("create", "edit", "delete")


@tagged("post_install", "-at_install")
class TestMethodStepAccess(MasterDataCase, PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.step = cls.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": cls.method.id,
                "sequence": 1,
                "duration_minutes": 15,
                "instruction": "Weigh the sample.",
                "note": "Use a clean crucible.",
            }
        )
        cls.tester = cls.create_person(
            "Le Van Cuong",
            cls.chemistry,
            "cuong.le",
            permissions=("sample_test.read.all", "test_result.create.all", "test_result.edit.all"),
        )

    def user_with(self, *groups):
        login = "_".join(group.rsplit(".", 1)[-1] for group in groups) or "internal"
        return new_test_user(self.env, login=login, groups=",".join(("base.group_user", *groups)))

    def step_groups(self):
        return [f"sol_laboratory.group_permission_testing_method_step_{action}_all" for action in STEP_PERMISSIONS]

    def changes(self, records, method):
        """Every way of creating, editing and deleting a step, directly and through its method."""
        steps = records.env[MODEL_TESTING_METHOD_STEP]
        step = self.step.with_env(records.env)
        new = {"method_id": self.method.id, "sequence": 2, "duration_minutes": 5, "instruction": "Dry it."}
        return {
            "create": lambda: steps.create(new),
            "write": lambda: step.write({"duration_minutes": 20}),
            "unlink": step.unlink,
            "create through the method": lambda: method.write(
                {"step_ids": [Command.create({"sequence": 3, "duration_minutes": 5, "instruction": "Ash it."})]}
            ),
            "write through the method": lambda: method.write(
                {"step_ids": [Command.update(persisted_id(self.step), {"duration_minutes": 20})]}
            ),
            "delete through the method": lambda: method.write({"step_ids": [Command.delete(persisted_id(self.step))]}),
        }

    def assert_refused(self, user):
        method = self.method.with_user(user)
        for name, change in self.changes(method, method).items():
            with self.subTest(change=name), self.assertRaises(AccessError):
                change()
        self.env.invalidate_all()
        self.assertEqual(
            [self.step.duration_minutes, len(self.method.step_ids)], [15, 1], "a refused change must leave the steps"
        )

    def test_every_internal_user_reads_the_steps(self):
        user = self.user_with()
        step = self.step.with_user(user)

        self.assertEqual(
            step.read(["sequence", "duration_minutes", "instruction", "note"])[0],
            {
                "id": self.step.id,
                "sequence": 1,
                "duration_minutes": 15,
                "instruction": "Weigh the sample.",
                "note": "Use a clean crucible.",
            },
        )
        self.assertEqual(self.method.with_user(user).step_ids, self.step)

    def test_a_tester_cannot_change_a_step(self):
        self.assertEqual(self.as_person(self.step, self.tester).instruction, "Weigh the sample.")
        self.assert_refused(self.tester.user_id)

    def test_editing_a_method_does_not_change_its_steps_without_the_step_permissions(self):
        self.assert_refused(self.user_with("sol_laboratory.group_permission_testing_method_edit_all"))

    def test_the_administrator_manages_steps(self):
        administrator = self.env.ref("base.user_admin")
        method = self.method.with_user(administrator)
        changes = self.changes(method, method)

        changes["create"]()
        changes["write"]()
        changes["create through the method"]()
        changes["write through the method"]()
        self.env.invalidate_all()

        self.assertEqual(self.method.step_ids.mapped("sequence"), [1, 2, 3])
        self.assertEqual(self.step.duration_minutes, 20)
        changes["delete through the method"]()
        self.assertFalse(self.step.exists())

    def test_step_permissions_do_not_change_the_method(self):
        user = self.user_with(*self.step_groups())
        method = self.method.with_user(user)

        method.env[MODEL_TESTING_METHOD_STEP].create(
            {"method_id": self.method.id, "sequence": 2, "duration_minutes": 5, "instruction": "Dry it."}
        )
        for name, change in {
            "write": lambda: method.write({"name": "Renamed"}),
            "archive": method.action_archive,
            "unlink": method.unlink,
        }.items():
            with self.subTest(change=name), self.assertRaises(AccessError):
                change()
        self.env.invalidate_all()
        self.assertEqual([self.method.name, self.method.active], ["Lead by AAS", True])

    def test_portal_and_public_users_cannot_read_steps(self):
        portal = new_test_user(self.env, login="portal.customer", groups="base.group_portal")
        for user in (portal, self.env.ref("base.public_user")):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.step.with_user(user).read(["instruction"])

    def test_the_administrator_role_holds_the_step_permissions(self):
        administrator = self.env.ref("sol_laboratory.role_administrator")
        for action in STEP_PERMISSIONS:
            with self.subTest(action=action):
                permission = reference_as(
                    self.env[MODEL_PERMISSION], f"sol_laboratory.permission_testing_method_step_{action}_all"
                )
                self.assertIn(permission, administrator.permission_ids)
                self.assertEqual(
                    permission.group_id,
                    reference_as(
                        self.env[MODEL_RES_GROUPS], f"sol_laboratory.group_permission_testing_method_step_{action}_all"
                    ),
                )
