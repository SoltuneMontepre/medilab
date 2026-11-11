from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import tagged
from odoo.tools import SQL

from .location_case import LocationCase
from .schedule_invariants_case import ScheduleInvariantsCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_TESTING_METHOD_STEP
from odoo.addons.sol_laboratory.constants.scheduling import CALENDAR_SYNC_CONTEXT, CALENDAR_SYNC_TOKEN

SLOT = timedelta(minutes=15)
OFF_BOUNDARY = MONDAY + timedelta(hours=2, minutes=7)
OVERLAP_CONSTRAINTS = {
    "medilab_machine_booking": "medilab_machine_booking_no_overlap",
    "calendar_event": "calendar_event_location_no_overlap",
}


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleInvariants(ScheduleInvariantsCase, LocationCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": cls.method.id,
                "sequence": 1,
                "duration_minutes": 20,
                "instruction": "Prepare the sample",
                "location_id": cls.room.id,
            }
        )

    def drop_overlap_constraints(self):
        # Only inside a rolled-back savepoint: the database refuses the overlaps P1 and P2 look for.
        for table, constraint in OVERLAP_CONSTRAINTS.items():
            self.env.cr.execute(
                SQL("ALTER TABLE %s DROP CONSTRAINT %s", SQL.identifier(table), SQL.identifier(constraint))
            )

    def overlap_constraints(self):
        self.env.cr.execute(
            SQL("SELECT conname FROM pg_constraint WHERE conname IN %s", tuple(OVERLAP_CONSTRAINTS.values()))
        )
        return {name for (name,) in self.env.cr.fetchall()}

    def test_each_invariant_fails_on_a_schedule_that_breaks_it_and_the_broken_state_is_rolled_back(self):
        second_test = self.new_test()
        self.testing_task(self.test, self.tester)
        self.testing_task(second_test, self.other_tester)
        first = self.schedule(self.test, self.tester)
        second = self.schedule(second_test, self.other_tester)
        tests = self.test | second_test
        self.assertEqual((first.machine_id, first.starts_at, second.machine_id), (self.fast, MONDAY, self.fast))
        self.assert_schedule_invariants(tests)
        before = self.graph(tests)

        def overlap_on_one_machine():
            self.drop_overlap_constraints()
            second._set({"starts_at": first.starts_at, "ends_at": first.ends_at})

        def overlap_in_one_room():
            self.drop_overlap_constraints()
            second._set({"machine_id": self.slow.id, "starts_at": first.starts_at, "ends_at": first.ends_at})

        def unsync_the_calendar():
            event = first.calendar_event_id.sudo().with_context(**{CALENDAR_SYNC_CONTEXT: CALENDAR_SYNC_TOKEN})
            event.write({"start": MONDAY + SLOT, "stop": MONDAY + 4 * SLOT})

        def end_after_the_calibration():
            self.env.cr.execute(
                SQL(
                    "UPDATE %s SET next_calibration_date = %s WHERE id = %s",
                    SQL.identifier(self.fast._table),
                    "2026-10-01",
                    self.fast.id,
                )
            )
            self.fast.invalidate_recordset(["next_calibration_date"])

        corruptions = {
            "P1": overlap_on_one_machine,
            "P2": overlap_in_one_room,
            "P3": lambda: second._set({"starts_at": OFF_BOUNDARY, "ends_at": OFF_BOUNDARY + 3 * SLOT}),
            "P4": lambda: self.env[MODEL_MACHINE_BOOKING].create(
                {"machine_id": self.fast.id, "sample_test_id": self.test.id, "person_id": self.tester.id}
            ),
            "P5": lambda: first._set({"person_id": self.other_tester.id}),
            "P6": lambda: self.test.sudo().write({"status": "waiting"}),
            "P7": unsync_the_calendar,
            "P8": lambda: self.test.sudo().write({"status": "cancelled"}),
            "P9": end_after_the_calibration,
        }
        for invariant, corrupt in corruptions.items():
            with self.subTest(invariant=invariant):
                with self.rolled_back():
                    corrupt()
                    with self.assertRaisesRegex(AssertionError, f"{invariant}:"):
                        self.assert_schedule_invariants(tests)
                self.assertEqual(self.graph(tests), before)
                self.assertEqual(self.overlap_constraints(), set(OVERLAP_CONSTRAINTS.values()))
                self.assert_schedule_invariants(tests)
