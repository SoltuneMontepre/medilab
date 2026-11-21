import importlib.util
from pathlib import Path

from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDemoRolePermissions(TransactionCase):
    def test_upgrade_restores_workflow_permissions_without_widening_roles(self):
        module_path = get_module_path("sol_demo")
        assert module_path is not None
        migration_path = Path(module_path) / "migrations" / "20.0.1.44.0" / "post-migrate.py"
        self.assertTrue(migration_path.is_file(), "The demo role permission upgrade migration must exist.")
        spec = importlib.util.spec_from_file_location("sol_demo_role_permission_migration", migration_path)
        assert spec is not None
        assert spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        head_role = self.env.ref("sol_demo.demo_role_head_of_department")
        sales_role = self.env.ref("sol_demo.demo_role_sales")
        staff_role = self.env.ref("sol_demo.demo_role_sample_delivery_staff")
        head_permissions = self.env["medilab.permission"].browse(
            [
                self.env.ref("sol_laboratory.permission_plan_revision_read_own_department").id,
                self.env.ref("sol_laboratory.permission_plan_revision_move_read_own_department").id,
            ]
        )
        delivery_permission = self.env.ref("sol_laboratory.permission_test_report_deliver_all")
        sales_permissions = self.env["medilab.permission"].browse(
            [
                self.env.ref("sol_laboratory.permission_plan_revision_read_all").id,
                self.env.ref("sol_laboratory.permission_plan_revision_move_read_all").id,
            ]
        )
        unrelated_permission = head_role.permission_ids[:1]
        head_role.permission_ids -= head_permissions
        sales_role.permission_ids -= sales_permissions
        staff_role.permission_ids -= delivery_permission

        migration.migrate(self.env.cr, "20.0.1.43.0")
        self.env.invalidate_all()
        migration.migrate(self.env.cr, "20.0.1.43.0")
        self.env.invalidate_all()

        self.assertEqual(head_permissions & head_role.permission_ids, head_permissions)
        self.assertNotIn(self.env.ref("sol_laboratory.permission_plan_revision_read_all"), head_role.permission_ids)
        self.assertEqual(sales_permissions & sales_role.permission_ids, sales_permissions)
        self.assertIn(delivery_permission, staff_role.permission_ids)
        self.assertIn(unrelated_permission, head_role.permission_ids)
        self.assertTrue(
            self.env.ref("sol_demo.demo_res_users_head_of_department").has_group(
                "sol_laboratory.group_permission_plan_revision_read_own_department"
            )
        )
        self.assertTrue(
            self.env.ref("sol_demo.demo_res_users_head_of_department").has_group(
                "sol_laboratory.group_permission_plan_revision_move_read_own_department"
            )
        )
        self.assertTrue(
            self.env.ref("sol_demo.demo_res_users_sample_delivery_staff").has_group(
                "sol_laboratory.group_permission_test_report_deliver_all"
            )
        )
        self.assertTrue(
            self.env.ref("sol_demo.demo_res_users_sales").has_group(
                "sol_laboratory.group_permission_plan_revision_read_all"
            )
        )
        self.assertTrue(
            self.env.ref("sol_demo.demo_res_users_sales").has_group(
                "sol_laboratory.group_permission_plan_revision_move_read_all"
            )
        )
        self.assertFalse(
            self.env.ref("sol_demo.demo_res_users_tester").has_group(
                "sol_laboratory.group_permission_test_report_deliver_all"
            )
        )
