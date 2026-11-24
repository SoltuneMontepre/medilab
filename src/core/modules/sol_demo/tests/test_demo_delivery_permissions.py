from pathlib import Path

from odoo.exceptions import AccessError
from odoo.modules.module import load_script
from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_RES_USERS, MODEL_ROLE, MODEL_SAMPLE
from odoo.addons.sol_laboratory.services.model_lookup import reference_as

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.46.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestDemoDeliveryPermissions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff_role = reference_as(cls.env[MODEL_ROLE], "sol_demo.demo_role_sample_delivery_staff")
        cls.staff_user = reference_as(cls.env[MODEL_RES_USERS], "sol_demo.demo_res_users_sample_delivery_staff")
        cls.edit_permission = reference_as(cls.env[MODEL_PERMISSION], "sol_laboratory.permission_sample_edit_all")

    def assert_handover_permissions(self):
        for permission in (
            "sample_handover_read_all",
            "sample_handover_create_all",
            "sample_handover_edit_all",
            "handover_record_read_all",
            "handover_record_create_all",
            "handover_record_edit_all",
            "test_report_deliver_all",
        ):
            with self.subTest(permission=permission):
                self.assertTrue(self.staff_user.has_group(f"sol_laboratory.group_permission_{permission}"))

    def test_seed_denies_sample_edits(self):
        self.assert_handover_permissions()
        sample = reference_as(self.env[MODEL_SAMPLE], "sol_demo.demo_sample_cabbage_received").with_user(
            self.staff_user
        )
        with self.assertRaises(AccessError):
            sample.write({"disposal_note": "Updated method"})

    def test_seed_denies_disposal_of_a_sample_past_retention(self):
        sample = reference_as(self.env[MODEL_SAMPLE], "sol_demo.demo_sample_retained_over").with_user(self.staff_user)
        with self.assertRaises(AccessError):
            sample.action_dispose(method="Organic waste")

    def test_upgrade_removes_only_sample_edit_from_the_delivery_role(self):
        other_roles = [
            reference_as(self.env[MODEL_ROLE], f"sol_demo.demo_role_{role}")
            for role in ("sales", "tester", "head_of_department")
        ]
        other_permissions = {role: role.permission_ids for role in other_roles}
        custom_permission = reference_as(self.env[MODEL_PERMISSION], "sol_laboratory.permission_plan_revision_read_all")
        self.staff_role.permission_ids |= self.edit_permission | custom_permission
        expected = self.staff_role.permission_ids - self.edit_permission

        self.assertTrue(POST_MIGRATE.is_file(), "The demo delivery permission upgrade migration must exist.")
        migration = load_script(str(POST_MIGRATE), "demo_delivery_permissions_post")
        migration.migrate(self.env.cr, "20.0.1.45.0")
        migration.migrate(self.env.cr, "20.0.1.45.0")
        self.env.invalidate_all()

        self.assertEqual(self.staff_role.permission_ids, expected)
        self.assertEqual({role: role.permission_ids for role in other_roles}, other_permissions)
        self.assertFalse(self.staff_user.has_group("sol_laboratory.group_permission_sample_edit_all"))
        self.assert_handover_permissions()
