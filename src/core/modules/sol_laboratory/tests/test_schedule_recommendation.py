import re
from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .cross_department_case import CrossDepartmentCase
from .location_case import LocationCase
from .schedule_invariants_case import WEEKDAYS
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_SAMPLE_TEST,
    MODEL_SUBCONTRACTOR,
    MODEL_TESTING_METHOD_STEP,
)

SLOT = timedelta(minutes=15)
TUESDAY = MONDAY + timedelta(days=1)
BOOKING_FIELDS = ["status", "machine_id", "person_id", "starts_at", "ends_at", "calendar_event_id"]


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleRecommendation(CrossDepartmentCase, LocationCase):
    def test_the_machine_that_finishes_first_wins_over_the_one_that_starts_first(self):
        (self.fast | self.slow).write({"status": "under_repair"})
        long_run, short_run = self.env[MODEL_MACHINE].create(
            [{"code": "AAS-120", "name": "AAS 120"}, {"code": "AAS-40", "name": "AAS 40"}]
        )
        self.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            [
                {"parameter_method_id": self.pair.id, "machine_id": long_run.id, "run_minutes": 120},
                {"parameter_method_id": self.pair.id, "machine_id": short_run.id, "run_minutes": 40},
            ]
        )
        self.occupy(short_run, MONDAY, MONDAY + 2 * SLOT)
        self.testing_task(self.test, self.tester)
        bookings = self.env[MODEL_MACHINE_BOOKING]
        self.assertEqual(bookings._free_slot(long_run, 8 * SLOT, self.tester, self.test.due_date), MONDAY)
        self.assertEqual(
            (self.test.recommended_machine_id, self.test.recommended_start, self.test.recommended_end),
            (short_run, MONDAY + 2 * SLOT, MONDAY + 5 * SLOT),
        )
        booking = self.schedule(self.test, self.tester)
        self.assertEqual(
            (booking.machine_id, booking.starts_at, booking.ends_at), (short_run, MONDAY + 2 * SLOT, MONDAY + 5 * SLOT)
        )
        self.assertFalse(long_run.booking_ids)
        self.assert_schedule_invariants(self.test)

    def test_a_test_waits_for_its_own_departments_machines_rather_than_take_another_departments(self):
        for machine in (self.fast, self.slow):
            self.occupy(machine, MONDAY, MONDAY + timedelta(hours=9))
        self.testing_task(self.test, self.tester)
        free = self.env[MODEL_MACHINE_BOOKING]._free_slot(
            self.microbiology_machine, 3 * SLOT, self.tester, self.test.due_date
        )
        self.assertEqual(free, MONDAY)
        tuesday = MONDAY + timedelta(days=1)
        self.assertEqual(
            (self.test.recommended_machine_id, self.test.recommended_method_id, self.test.recommended_start),
            (self.fast, self.pair, tuesday),
        )
        booking = self.schedule(self.test, self.tester)
        self.assertEqual((booking.machine_id, booking.starts_at), (self.fast, tuesday))
        self.assertEqual(self.test.parameter_method_id, self.pair)
        self.assertFalse(self.microbiology_machine.booking_ids)
        self.assert_schedule_invariants(self.test)

    def running_and_waiting_on_fast(self):
        """A running booking of the tester from 08:00 and a waiting one of the other tester after it, both on fast."""
        self.slow.status = "under_repair"
        running_test, waiting_test = self.test, self.new_test()
        self.testing_task(running_test, self.tester)
        self.testing_task(waiting_test, self.other_tester)
        running = self.schedule(running_test, self.tester)
        waiting = self.schedule(waiting_test, self.other_tester)
        self.assertEqual((running.machine_id, running.starts_at), (self.fast, MONDAY))
        self.assertEqual((waiting.machine_id, waiting.starts_at), (self.fast, MONDAY + 3 * SLOT))
        running.with_user(self.tester.user_id).action_start()
        self.slow.status = "in_use"
        return running, waiting

    def test_a_machine_out_of_use_hands_its_scheduled_bookings_on_and_keeps_its_running_one(self):
        for status in ("under_repair", "retired"):
            with self.subTest(status=status), self.rolled_back():
                running, waiting = self.running_and_waiting_on_fast()
                before = running.read(BOOKING_FIELDS)
                self.fast.status = status
                self.assertEqual(running.read(BOOKING_FIELDS), before)
                self.assertEqual(running.status, "in_progress")
                self.assertEqual(
                    (waiting.status, waiting.machine_id, waiting.starts_at, waiting.ends_at),
                    ("scheduled", self.slow, MONDAY, MONDAY + 5 * SLOT),
                )
                later = self.new_test()
                self.testing_task(later, self.tester)
                self.assertEqual(later.recommended_machine_id, self.slow)
                self.assert_schedule_invariants(running.sample_test_id | waiting.sample_test_id | later)

    def test_a_machine_with_open_bookings_cannot_be_archived(self):
        running, waiting = self.running_and_waiting_on_fast()
        tests = running.sample_test_id | waiting.sample_test_id
        before = self.graph(tests)
        with self.assertRaisesRegex(UserError, "cannot be archived") as refusal, self.rolled_back():
            self.fast.active = False
        for booking in (running, waiting):
            self.assertIn(booking.display_name, str(refusal.exception))
        self.assertEqual(self.graph(tests), before)
        self.assertEqual((self.fast.active, self.fast.status), (True, "in_use"))
        self.assert_schedule_invariants(tests)

    def test_a_booking_whose_machine_is_lost_with_no_other_goes_back_to_the_queue_and_frees_its_calendar(self):
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": self.method.id,
                "sequence": 1,
                "duration_minutes": 20,
                "instruction": "Prepare the sample",
                "location_id": self.room.id,
            }
        )
        self.slow.status = "under_repair"
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        event, rooms = booking.calendar_event_id, booking.room_event_ids
        self.assertTrue(event)
        self.assertEqual(rooms.location_id, self.room)
        self.assertEqual((task.planned_start, task.planned_end), (MONDAY, MONDAY + 3 * SLOT))
        self.assert_schedule_invariants(self.test)

        self.fast.status = "under_repair"
        self.assertEqual((booking.status, booking.starts_at, booking.ends_at), ("queued", False, False))
        self.assertEqual(booking.person_id, self.tester)
        self.assertFalse(booking.calendar_event_id)
        self.assertFalse(booking.room_event_ids)
        self.assertFalse(event.exists())
        self.assertFalse(rooms.exists())
        self.assertEqual((task.planned_start, task.planned_end), (False, False))
        self.assertEqual((self.test.status, task.status, task.assignee_id), ("assigned", "assigned", self.tester))
        self.assertTrue(self.test.outsourcing_suggested)
        self.assert_schedule_invariants(self.test)

    def recommendation(self, test):
        test.invalidate_recordset()
        return test.recommended_machine_id, test.recommended_start, test.recommended_end

    def test_a_parameter_no_department_machine_runs_is_suggested_for_outsourcing_and_cannot_be_scheduled(self):
        arsenic = self.create_parameter("Arsenic (As)", self.group)
        subcontractor_id, _name = self.env[MODEL_SUBCONTRACTOR].name_create("Northern Testing")
        outside = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": arsenic.id,
                "method_id": self.method.id,
                "subcontractor_id": subcontractor_id,
            }
        )
        self.offer(arsenic, self.sample_type, outside)
        test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": arsenic.id})
        self.testing_task(test, self.tester)
        self.assertEqual(self.recommendation(test), (self.env[MODEL_MACHINE], False, False))
        self.assertTrue(test.outsourcing_suggested)
        self.assertEqual(test.subcontracted_method_ids, outside)
        message = f"No machine can finish {test.display_name} before its due date."
        with self.assertRaisesRegex(UserError, re.escape(message)), self.rolled_back():
            self.schedule(test, self.tester)
        self.assertFalse(test.booking_ids)
        self.assertEqual(test.status, "assigned")
        self.assert_schedule_invariants(test)

    def test_a_short_run_fills_a_gap_a_longer_run_skips_whichever_is_scheduled_first(self):
        self.slow.status = "under_repair"
        copper = self.create_parameter("Copper (Cu)", self.group)
        copper_way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": copper.id,
                "method_id": self.method.id,
                "department_id": self.department.id,
            }
        )
        self.offer(copper, self.sample_type, copper_way)
        self.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            {"parameter_method_id": copper_way.id, "machine_id": self.fast.id, "run_minutes": 25}
        )
        self.occupy(self.fast, MONDAY, MONDAY + 3 * SLOT)
        self.occupy(self.fast, MONDAY + 5 * SLOT, MONDAY + 8 * SLOT)
        lead = self.new_test()
        copper_test = self.env[MODEL_SAMPLE_TEST].create(
            {"sample_id": self.create_request().sample_ids.id, "parameter_id": copper.id}
        )
        self.testing_task(lead, self.tester)
        self.testing_task(copper_test, self.other_tester)
        runs = {"lead": (lead, self.tester), "copper": (copper_test, self.other_tester)}
        for order in (("lead", "copper"), ("copper", "lead")):
            with self.subTest(order=order), self.rolled_back():
                for name in order:
                    self.schedule(*runs[name])
                lead_booking, copper_booking = lead.booking_ids, copper_test.booking_ids
                self.assertEqual(
                    (lead_booking.machine_id, lead_booking.starts_at, lead_booking.ends_at),
                    (self.fast, MONDAY + 8 * SLOT, MONDAY + 11 * SLOT),
                )
                self.assertEqual(
                    (copper_booking.machine_id, copper_booking.starts_at, copper_booking.ends_at),
                    (self.fast, MONDAY + 3 * SLOT, MONDAY + 5 * SLOT),
                )
                self.assert_schedule_invariants(lead | copper_test)

    def test_a_machine_takes_bookings_until_the_end_of_its_calibration_date_in_a_utc_laboratory(self):
        # The demo data puts the laboratory in Vietnam; this case is the laboratory in UTC.
        self.env.company.tz = "UTC"
        self.slow.status = "under_repair"
        self.fast.service_ids = [
            Command.create({"kind": "calibration", "service_date": "2025-10-12", "next_due_date": "2026-10-12"})
        ]
        self.assertEqual(self.fast._usable_until(), datetime(2026, 10, 13, 0, 0))
        # The company calendar gives 8 hours a day centred on noon: the tester works 08:00-16:00.
        closing = MONDAY + timedelta(hours=8)
        evening = closing - 3 * SLOT
        with self.subTest(busy_until="15:15"), self.rolled_back():
            self.occupy(self.fast, MONDAY, evening)
            self.testing_task(self.test, self.tester)
            self.assertEqual(self.recommendation(self.test), (self.fast, evening, closing))
            booking = self.schedule(self.test, self.tester)
            self.assertEqual((booking.starts_at, booking.ends_at), (evening, closing))
            self.assert_schedule_invariants(self.test)
        with self.subTest(busy_until="16:00"), self.rolled_back():
            self.occupy(self.fast, MONDAY, closing)
            self.testing_task(self.test, self.tester)
            self.assertEqual(self.recommendation(self.test), (self.env[MODEL_MACHINE], False, False))
            self.assertTrue(self.test.outsourcing_suggested)
            self.fast.service_ids.write({"next_due_date": "2026-10-13"})
            self.assertEqual(self.recommendation(self.test), (self.fast, TUESDAY, TUESDAY + 3 * SLOT))
            self.assert_schedule_invariants(self.test)

    def test_a_test_is_booked_outside_its_persons_leave_and_the_calendars_days_off(self):
        self.slow.status = "under_repair"
        office_hours = self.create_calendar(
            "Office hours in UTC", [(day, 8, 12) for day in WEEKDAYS] + [(day, 13, 17) for day in WEEKDAYS]
        )
        (self.tester | self.other_tester).write({"resource_calendar_id": office_hours.id})
        leaves = self.env["resource.calendar.leaves"]
        other = self.new_test()
        with self.subTest(leave="personal, Monday morning"), self.rolled_back():
            leaves.create(
                {
                    "name": "Medical appointment",
                    "calendar_id": office_hours.id,
                    "resource_id": self.tester.resource_id.id,
                    "date_from": MONDAY,
                    "date_to": MONDAY + timedelta(hours=4),
                }
            )
            self.testing_task(self.test, self.tester)
            self.testing_task(other, self.other_tester)
            afternoon = MONDAY + timedelta(hours=5)
            self.assertEqual(self.recommendation(self.test), (self.fast, afternoon, afternoon + 3 * SLOT))
            self.assertEqual(self.recommendation(other), (self.fast, MONDAY, MONDAY + 3 * SLOT))
            booking = self.schedule(self.test, self.tester)
            self.assertEqual((booking.starts_at, booking.ends_at), (afternoon, afternoon + 3 * SLOT))
            self.assert_schedule_invariants(self.test)
        with self.subTest(leave="the whole calendar, Monday"), self.rolled_back():
            leaves.create(
                {
                    "name": "Public holiday",
                    "calendar_id": office_hours.id,
                    "date_from": datetime(2026, 10, 12),
                    "date_to": datetime(2026, 10, 12, 23, 59, 59),
                }
            )
            self.testing_task(self.test, self.tester)
            booking = self.schedule(self.test, self.tester)
            self.assertEqual((booking.starts_at, booking.ends_at), (TUESDAY, TUESDAY + 3 * SLOT))
            self.assert_schedule_invariants(self.test)
