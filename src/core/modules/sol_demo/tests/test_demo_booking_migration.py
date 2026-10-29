from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from freezegun import freeze_time

from odoo.modules.migration import MigrationManager
from odoo.modules.module import load_script
from odoo.tests import tagged

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD_MACHINE,
)
from odoo.addons.sol_laboratory.tests.scheduling_case import SchedulingCase

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
BOOKING_XML_ID = "demo_machine_booking_lead_queued"


@tagged("post_install", "-at_install")
class TestDemoBookingMigration(SchedulingCase):
    def setUp(self):
        super().setUp()
        self.env.cr.execute("SELECT NOW() AT TIME ZONE 'UTC'")
        row = self.env.cr.fetchone()
        if row is None:
            self.fail("The database clock query returned no row.")
        self.now = row[0].replace(microsecond=0)
        self.test.due_date = self.now + timedelta(minutes=30)
        self.env[MODEL_PARAMETER_METHOD_MACHINE].search([("machine_id", "=", self.fast.id)]).run_minutes = 15
        task = self.testing_task(self.test, self.tester)
        self.booking = self.env[MODEL_MACHINE_BOOKING].create(
            {
                "machine_id": self.fast.id,
                "sample_test_id": self.test.id,
                "task_id": task.id,
                "person_id": self.tester.id,
                "queued_at": self.now,
            }
        )
        self.xml_id = self.env["ir.model.data"].search([("module", "=", "sol_demo"), ("name", "=", BOOKING_XML_ID)])
        self.xml_id.res_id = self.booking.id
        self.env.flush_all()

    def pre_migrate(self):
        load_script(str(MIGRATIONS / "20.0.1.10.0" / "pre-migrate.py"), "demo_booking_pre").migrate(
            self.env.cr, "20.0.1.9.0"
        )
        self.env.invalidate_all()

    def test_upgrade_keeps_a_schedulable_old_fixture_queued_through_calibration_loading(self):
        # Recreate the missing calibration loaded on upgrade, before the synthetic queued booking can be replanned.
        calibration = self.env.ref("sol_demo.demo_machine_service_aas_calibration")
        with patch.object(type(self.booking), "_process_queue"):
            calibration.unlink()
        package = SimpleNamespace(
            name="sol_demo", load_state="to upgrade", load_version="20.0.1.9.0", manifest={"version": "20.0.1.11.0"}
        )
        manager = MigrationManager(self.env.cr, [package])
        with (
            freeze_time(self.now),
            patch.object(type(self.booking), "_working_time", return_value=[(self.now, self.now + timedelta(days=1))]),
        ):
            self.assertTrue(self.booking._recommend(self.test, self.tester, self.department))
            manager.migrate_module(package, "pre")
            # Registry setup between migration stages invalidates the ORM cache before loading the module's data.
            self.env.invalidate_all()
            self.assertLess(self.test.due_date, self.now)
            self.assertEqual(self.booking.due_date, self.test.due_date)
            self.assertTrue(self.test.outsourcing_suggested)

            manager.migrate_module(package, "post")

        self.env.flush_all()
        self.env.invalidate_all()
        self.assertTrue(self.env.ref("sol_demo.demo_machine_service_aas_calibration").exists())
        self.assertEqual(self.booking.status, "queued")
        self.assertFalse(self.booking.starts_at)
        self.assertFalse(self.booking.ends_at)
        self.assertTrue(self.test.outsourcing_suggested)
        self.assertEqual(self.test.due_date, self.now + timedelta(minutes=30))
        self.assertEqual(self.booking.due_date, self.test.due_date)
        self.assertEqual(self.booking.task_id.deadline, self.test.due_date)

    def test_pre_migration_keeps_other_queued_tests_unchanged(self):
        other = self.new_test(self.now + timedelta(days=2))
        task = self.testing_task(other, self.other_tester)
        booking = self.env[MODEL_MACHINE_BOOKING].create(
            {
                "machine_id": self.slow.id,
                "sample_test_id": other.id,
                "task_id": task.id,
                "person_id": self.other_tester.id,
            }
        )
        self.env.flush_all()
        original = (other.due_date, other.outsourcing_suggested, booking.due_date)

        self.pre_migrate()

        self.assertEqual((other.due_date, other.outsourcing_suggested, booking.due_date), original)
        self.assertLess(self.test.due_date, self.now)

    def test_migrations_preserve_a_fixture_already_used_in_a_demo(self):
        for status in ("scheduled", "in_progress", "done", "cancelled"):
            with self.subTest(status=status):
                self.booking._set(
                    {"status": status, "starts_at": self.now, "ends_at": self.now + timedelta(minutes=15)}
                )
                self.env.flush_all()
                original = (self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline)

                self.pre_migrate()
                load_script(str(MIGRATIONS / "20.0.1.11.0" / "post-migrate.py"), "demo_booking_post").migrate(
                    self.env.cr, "20.0.1.9.0"
                )

                self.assertEqual(self.booking.status, status)
                self.assertEqual(
                    (self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline), original
                )

    def test_migrations_accept_a_missing_fixture(self):
        self.xml_id.unlink()
        original = (self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline)

        self.pre_migrate()
        load_script(str(MIGRATIONS / "20.0.1.11.0" / "post-migrate.py"), "demo_booking_post").migrate(
            self.env.cr, "20.0.1.9.0"
        )

        self.assertEqual((self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline), original)

    def test_a_fresh_install_does_not_run_upgrade_migrations(self):
        package = SimpleNamespace(
            name="sol_demo", load_state="to install", load_version=False, manifest={"version": "20.0.1.11.0"}
        )
        original = (self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline)

        # Odoo removes this installation-only registry state before running post-install tests.
        with patch.object(self.env.registry, "_force_upgrade_scripts", set(), create=True):
            manager = MigrationManager(self.env.cr, [package])
            manager.migrate_module(package, "pre")
            manager.migrate_module(package, "post")

        self.assertEqual((self.test.due_date, self.test.outsourcing_suggested, self.booking.task_id.deadline), original)
