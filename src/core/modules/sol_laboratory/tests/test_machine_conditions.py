from datetime import datetime, timedelta
from pathlib import Path

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.modules.module import load_script
from odoo.tests import tagged
from odoo.tools import mute_logger

from .result_case import ResultCase
from .scheduling_case import MONDAY, calibrated
from odoo.addons.sol_laboratory.constants.jobs import MACHINE_BOOKINGS_OVERRUN_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.settings import CALIBRATION_WARNING_PARAMETER

SLOT = timedelta(minutes=15)
PRE_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.40.0" / "pre-migrate.py"
OVERRUN_EVENT = "sol_laboratory.event_machine_booking_overrun"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestMachineConditions(ResultCase):
    """The tester's lead test runs on AAS 1, 40 minutes a booking; AAS 2 is under repair."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"

    def recommend(self, test=None):
        found = self.env[MODEL_MACHINE_BOOKING]._recommend(test or self.test, self.tester, self.department)
        return found and found[1:3]

    def place(self, machine, start, end):
        """A scheduled booking of another test on the machine from start to end."""
        booking = self.env[MODEL_MACHINE_BOOKING].create(
            {"machine_id": machine.id, "sample_test_id": self.new_test().id}
        )
        booking._set({"status": "scheduled", "starts_at": start, "ends_at": end})
        return booking

    def service(self, machine, kind, day=None, **values):
        machine.service_ids = [Command.create({"kind": kind, "service_date": day, **values})]

    def test_a_booking_ending_after_the_calibration_is_refused(self):
        self.service(self.fast, "calibration", "2026-01-01", next_due_date="2026-10-13")
        until = self.fast._usable_until()

        self.assertEqual(self.place(self.fast, until - 3 * SLOT, until).ends_at, until)
        with self.assertRaisesRegex(ValidationError, "no valid calibration"), self.env.cr.savepoint():
            self.place(self.fast, until - SLOT, until + SLOT)

    def test_a_machine_never_calibrated_takes_no_booking_until_a_calibration_is_recorded(self):
        self.fast.status = "under_repair"
        machine = self.env[MODEL_MACHINE].create({"code": "AAS-NEW", "name": "AAS new"})
        self.env[MODEL_MACHINE_METHOD].create(
            {"method_id": self.pair.method_id.id, "machine_id": machine.id, "duration_minutes": 40}
        )

        self.assertEqual(machine._usable_until(), datetime.min)
        self.assertFalse(self.recommend())
        with self.assertRaisesRegex(ValidationError, "no valid calibration"), self.env.cr.savepoint():
            self.place(machine, MONDAY, MONDAY + SLOT)

        self.service(machine, "calibration", "2026-10-12", next_due_date="2027-10-12")
        self.assertEqual(self.recommend(), (machine, MONDAY))

    def test_overdue_maintenance_blocks_new_bookings_until_it_is_recorded(self):
        self.fast.maintenance_interval_days = 30
        self.service(self.fast, "maintenance", "2026-08-01")

        self.assertFalse(self.recommend())
        with self.assertRaisesRegex(ValidationError, "maintenance"), self.env.cr.savepoint():
            self.place(self.fast, MONDAY, MONDAY + SLOT)

        self.service(self.fast, "maintenance", "2026-10-12")
        self.assertEqual(self.recommend(), (self.fast, MONDAY))

    def test_planned_maintenance_reserves_its_downtime(self):
        booking = self.schedule(self.test, self.tester)
        self.assertEqual(booking.starts_at, MONDAY)

        self.service(self.fast, "maintenance", downtime_start=MONDAY, downtime_end=MONDAY + timedelta(hours=1))

        self.assertEqual((booking.status, booking.machine_id), ("scheduled", self.fast))
        self.assertEqual(booking.starts_at, MONDAY + timedelta(hours=1))
        self.assertFalse(self.fast.service_ids.filtered("downtime_start").service_date)
        with self.assertRaisesRegex(ValidationError, "planned service"), self.env.cr.savepoint():
            self.place(self.fast, MONDAY, MONDAY + SLOT)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.service(self.fast, "maintenance", downtime_start=MONDAY, downtime_end=MONDAY)
            self.env.flush_all()

    def test_a_repaired_machine_returns_to_use_only_after_a_later_calibration_or_maintenance(self):
        self.fast.status = "under_repair"
        self.service(self.fast, "repair", "2026-10-10")
        self.service(self.fast, "calibration", "2026-10-09", next_due_date="2027-10-09")

        with self.assertRaisesRegex(ValidationError, "after its repair"), self.env.cr.savepoint():
            self.fast.status = "in_use"

        self.service(self.fast, "maintenance", "2026-10-12")
        self.fast.status = "in_use"
        self.assertEqual(self.fast.status, "in_use")

    def test_entering_the_result_frees_the_machine_before_the_booking_ends(self):
        booking = self.schedule(self.test, self.tester)
        booking.with_user(self.tester.user_id).action_start()
        other = self.add_test()
        self.assertEqual(self.recommend(other), (self.fast, booking.ends_at))

        result = self.enter()

        self.assertEqual(result.booking_id, booking)
        self.assertEqual(booking.status, "done")
        self.assertEqual(self.recommend(other), (self.fast, MONDAY))

    def test_an_overrun_keeps_the_machine_and_notifies_the_tester_and_head_of_the_next_booking(self):
        self.department.manager_id = self.head.employee_id
        (self.tester | self.head).user_id.partner_id.email = "lab@anphu.example"
        booking = self.schedule(self.test, self.tester)
        booking.with_user(self.tester.user_id).action_start()
        later = self.place(self.fast, MONDAY + timedelta(hours=2), MONDAY + timedelta(hours=3))

        with freeze_time(MONDAY + timedelta(hours=1)):
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_OVERRUN_JOB)
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_OVERRUN_JOB)
            self.assertFalse(self.recommend(self.add_test()))
            (booking | later).invalidate_recordset(["machine_warning"])
            self.assertIn("end has passed", booking.machine_warning or "")
            self.assertIn("At risk", later.machine_warning or "")

        message = (
            self.env["mail.message"]
            .search([("model", "=", MODEL_MACHINE_BOOKING), ("subtype_id", "=", self.env.ref(OVERRUN_EVENT).id)])
            .filtered(lambda message: message.res_id in (booking | later).ids)
        )
        self.assertEqual(message.res_id, booking.id)
        self.assertIn(later.display_name, message.body or "")
        self.assertIn(self.tester.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertIn(self.head.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertEqual((booking.status, later.status, later.starts_at), ("in_progress", "scheduled", later.starts_at))

    def test_a_released_booking_is_not_an_overrun(self):
        booking = self.schedule(self.test, self.tester)
        booking.with_user(self.tester.user_id).action_start()
        booking.with_user(self.tester.user_id).action_done()

        with freeze_time(MONDAY + timedelta(hours=1)):
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_OVERRUN_JOB)

        self.assertFalse(
            self.env["mail.message"].search([("model", "=", MODEL_MACHINE_BOOKING), ("res_id", "=", booking.id)])
        )

    def test_bookings_warn_within_the_calibration_maintenance_and_repair_windows(self):
        self.fast.maintenance_interval_days = 30
        self.service(self.fast, "calibration", "2026-01-01", next_due_date="2026-10-15")
        self.service(self.fast, "maintenance", "2026-09-15")
        self.service(self.fast, "repair", "2026-10-10")
        self.service(self.fast, "calibration", "2026-10-11", next_due_date="2026-10-15")
        booking = self.schedule(self.test, self.tester)

        warning = booking.machine_warning or ""
        self.assertIn("calibration", warning)
        self.assertIn("maintenance", warning)
        self.assertIn("repaired", warning)

        self.env["ir.config_parameter"].set_int(CALIBRATION_WARNING_PARAMETER, 0)
        booking.invalidate_recordset(["machine_warning"])
        self.assertNotIn("calibration", booking.machine_warning or "")

    def test_a_negative_machine_warning_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "cannot be negative"):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"repair_warning_days": -1})

    def test_the_upgrade_links_a_result_only_to_the_one_booking_it_matches(self):
        booking = self.schedule(self.test, self.tester)
        result = self.enter()
        other = self.add_test()
        twin_machine = self.env[MODEL_MACHINE].create(calibrated({"code": "AAS-TWIN", "name": "AAS twin"}))
        ambiguous = self.enter(test=other, machine_id=twin_machine.id, started_at=MONDAY)
        for _index in range(2):
            twin = self.env[MODEL_MACHINE_BOOKING].create({"machine_id": twin_machine.id, "sample_test_id": other.id})
            twin._set({"status": "cancelled", "starts_at": MONDAY, "ends_at": MONDAY + SLOT})
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE medilab_test_result SET booking_id = NULL WHERE id IN %s", [(result.id, ambiguous.id)]
        )

        load_script(str(PRE_MIGRATE), "pre_migrate").migrate(self.env.cr, "20.0.1.36.0")
        self.env.invalidate_all()

        self.assertEqual(result.booking_id, booking)
        self.assertFalse(ambiguous.booking_id)
