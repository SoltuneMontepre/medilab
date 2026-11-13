from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import tagged

from .scheduling_case import SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_METHOD,
    MODEL_TESTING_METHOD,
)

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.36.0"


@tagged("post_install", "-at_install")
class TestMachineMethodMigration(SchedulingCase):
    """Before the upgrade, lead and copper share the case's method; AAS 1 runs lead in 40 minutes and copper in 55, and
    AAS 2 runs lead in 70."""

    def migrate(self, stage):
        load_script(str(MIGRATIONS / f"{stage}-migrate.py"), f"machine_method_{stage}").migrate(
            self.env.cr, "20.0.1.35.0"
        )
        self.env.invalidate_all()

    def test_upgrade_links_each_machine_to_its_methods_with_the_longest_run_time_and_fills_bookings(self):
        copper = self.create_parameter("Copper (Cu)", self.group)
        copper_way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": copper.id, "method_id": self.method.id, "department_id": self.department.id}
        )
        sensory = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 3215-79", "name": "Sensory evaluation", "field_id": self.testing_field.id}
        )
        odour = self.create_parameter("Odour", self.group)
        odour_way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": odour.id, "method_id": sensory.id, "department_id": self.department.id}
        )
        self.env[MODEL_MACHINE_METHOD].search([("method_id", "=", self.method.id)]).unlink()
        booking = self.env[MODEL_MACHINE_BOOKING].create({"machine_id": self.fast.id, "sample_test_id": self.test.id})
        self.test.parameter_method_id = self.pair
        cr = self.env.cr
        cr.execute(
            """
            CREATE TABLE medilab_parameter_method_machine (
                id SERIAL PRIMARY KEY, parameter_method_id INT4, machine_id INT4, run_minutes INT4
            )
            """
        )
        cr.execute(
            """
            INSERT INTO medilab_parameter_method_machine (parameter_method_id, machine_id, run_minutes)
            VALUES (%s, %s, 40), (%s, %s, 55), (%s, %s, 70)
            """,
            [self.pair.id, self.fast.id, copper_way.id, self.fast.id, self.pair.id, self.slow.id],
        )
        cr.execute("UPDATE medilab_machine_booking SET method_id = NULL WHERE id = %s", [booking.id])
        self.env.invalidate_all()

        with self.assertLogs(level="WARNING") as logged:
            self.migrate("post")

        links = self.env[MODEL_MACHINE_METHOD].search([("method_id", "=", self.method.id)])
        self.assertEqual(
            {(link.machine_id, link.duration_minutes, link.capacity) for link in links},
            {(self.fast, 55, 1), (self.slow, 70, 1)},
        )
        output = "\n".join(logged.output)
        self.assertIn("AAS-1 ran the ways of testing of TCVN 8126:2009 in 40 to 55 minutes", output)
        self.assertNotIn("AAS-2 ran", output)
        self.assertIn(f"Way of testing {odour_way.id} (Odour by TCVN 3215-79) has no machine", output)
        self.assertNotIn(f"Way of testing {copper_way.id} ", output)
        self.assertEqual(booking.method_id, self.method)
        cr.execute("SELECT to_regclass('medilab_parameter_method_machine')")
        self.assertEqual(cr.fetchone(), (None,))

    def test_upgrade_moves_the_link_permissions_with_their_holders_to_the_new_model(self):
        permission = self.env.ref("sol_laboratory.permission_machine_method_edit_all")
        group, roles = permission.group_id, permission.role_ids
        cr = self.env.cr
        # The permissions as the previous version shipped them.
        cr.execute(
            """
            UPDATE medilab_permission
               SET document_model = 'medilab.parameter.method.machine',
                   code = 'parameter.method.machine.' || action || '.all'
             WHERE document_model = 'medilab.machine.method'
            """
        )
        cr.execute(
            """
            UPDATE ir_model_data SET name = replace(name, 'machine_method_', 'parameter_method_machine_')
             WHERE module = 'sol_laboratory' AND name ~ '^(group_|access_)?permission_machine_method_'
            """
        )
        cr.execute(
            """
            UPDATE ir_access SET name = replace(name, 'machine.method.', 'parameter.method.machine.')
             WHERE name LIKE 'Permission: machine.method.%'
            """
        )

        self.migrate("pre")

        self.assertEqual(
            (permission.document_model, permission.code, permission.name, permission.group_id, permission.role_ids),
            ("medilab.machine.method", "machine.method.edit.all", "Edit machines for testing methods", group, roles),
        )
        self.assertEqual(group.name, "Permission: machine.method.edit.all")
        self.assertEqual(self.env.ref("sol_laboratory.group_permission_machine_method_edit_all"), group)
        access = self.env.ref("sol_laboratory.access_permission_machine_method_edit_all")
        self.assertEqual(access.name, "Permission: machine.method.edit.all")
