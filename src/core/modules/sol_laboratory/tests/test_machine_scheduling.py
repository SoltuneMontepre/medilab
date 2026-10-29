from datetime import timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_SUBCONTRACTOR,
    MODEL_TASK,
)

SLOT = timedelta(minutes=15)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestMachineScheduling(SchedulingCase):
    def queue(self, test, person, queued_at):
        task = self.testing_task(test, person)
        return self.env[MODEL_MACHINE_BOOKING].create(
            {
                "machine_id": self.fast.id,
                "sample_test_id": test.id,
                "task_id": task.id,
                "person_id": person.id,
                "queued_at": queued_at,
            }
        )

    def test_a_forty_minute_run_takes_three_slots(self):
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        self.assertEqual(booking.machine_id, self.fast)
        self.assertEqual(booking.status, "scheduled")
        self.assertEqual((booking.starts_at, booking.ends_at), (MONDAY, MONDAY + 3 * SLOT))
        self.assertEqual(self.test.parameter_method_id, self.pair)

    def test_the_recommendation_finishes_soonest_within_the_due_date(self):
        self.testing_task(self.test, self.tester)
        self.assertEqual(self.test.recommended_machine_id, self.fast)
        self.assertEqual(self.test.recommended_method_id, self.pair)
        self.assertEqual((self.test.recommended_start, self.test.recommended_end), (MONDAY, MONDAY + 3 * SLOT))

    def test_an_urgent_test_gets_the_next_free_slot_before_one_that_queued_earlier(self):
        self.slow.status = "under_repair"
        earlier = self.queue(self.new_test(), self.tester, MONDAY - timedelta(hours=1))
        urgent = self.queue(self.new_test(MONDAY + timedelta(hours=8)), self.other_tester, MONDAY)
        self.env[MODEL_MACHINE_BOOKING]._process_queue()
        self.assertEqual(urgent.starts_at, MONDAY)
        self.assertEqual(earlier.starts_at, MONDAY + 3 * SLOT)

    def test_bookings_of_one_machine_never_overlap(self):
        self.slow.status = "under_repair"
        second_test = self.new_test()
        self.testing_task(self.test, self.tester)
        self.testing_task(second_test, self.other_tester)
        first = self.schedule(self.test, self.tester)
        second = self.schedule(second_test, self.other_tester)
        self.assertEqual(second.starts_at, first.ends_at)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            second._set({"starts_at": first.starts_at, "ends_at": first.ends_at})
            self.env.flush_all()

    def test_a_machine_under_repair_gets_no_bookings_and_its_bookings_move_to_another(self):
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        self.fast.status = "under_repair"
        self.assertEqual(booking.machine_id, self.slow)
        self.assertEqual(booking.status, "scheduled")
        self.assertEqual((booking.starts_at, booking.ends_at), (MONDAY, MONDAY + 5 * SLOT))
        other = self.new_test()
        self.testing_task(other, self.other_tester)
        self.assertEqual(other.recommended_machine_id, self.slow)

    def test_a_machine_overdue_for_calibration_gets_no_bookings(self):
        self.fast.service_ids = [
            Command.create({"kind": "calibration", "service_date": "2025-10-01", "next_due_date": "2026-10-01"})
        ]
        self.testing_task(self.test, self.tester)
        self.assertEqual(self.test.recommended_machine_id, self.slow)

    def test_a_test_no_machine_can_finish_in_time_is_suggested_for_outsourcing(self):
        subcontractor_id, _name = self.env[MODEL_SUBCONTRACTOR].name_create("Northern Testing")
        outside = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": self.parameter.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "subcontractor_id": subcontractor_id,
            }
        )
        test = self.new_test(MONDAY + timedelta(minutes=30))
        self.testing_task(test, self.tester)
        self.assertTrue(test.outsourcing_suggested)
        self.assertFalse(test.recommended_machine_id)
        self.assertEqual(test.subcontracted_method_ids, outside)
        with self.assertRaises(UserError):
            self.schedule(test, self.tester)

    def test_a_scheduled_booking_shows_on_the_personal_schedule_the_machine_schedule_and_the_todo_list(self):
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        event = booking.calendar_event_id
        self.assertEqual(event.partner_ids, self.tester.user_id.partner_id)
        self.assertEqual((event.start, event.stop), (booking.starts_at, booking.ends_at))
        self.assertIn(booking, self.fast.booking_ids)
        todo = self.env[MODEL_TASK].with_user(self.tester.user_id).search([("is_mine", "=", True)])
        self.assertIn(task, todo)
        self.assertEqual((task.planned_start, task.planned_end), (booking.starts_at, booking.ends_at))
        self.assertFalse(self.env["calendar.event"].search([("medilab_task_id", "=", task.id)]))

    def test_cancelling_a_booking_gives_its_slot_to_the_queue(self):
        self.slow.status = "under_repair"
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        waiting = self.queue(self.new_test(MONDAY + timedelta(minutes=50)), self.other_tester, MONDAY)
        self.env[MODEL_MACHINE_BOOKING]._process_queue()
        self.assertEqual(waiting.status, "queued")
        self.assertTrue(waiting.sample_test_id.outsourcing_suggested)
        booking.with_user(self.tester.user_id).action_cancel()
        self.assertFalse(booking.calendar_event_id)
        self.assertEqual((waiting.status, waiting.starts_at), ("scheduled", MONDAY))
        self.assertFalse(waiting.sample_test_id.outsourcing_suggested)

    def test_moving_the_calendar_event_moves_the_booking_only_to_a_free_slot(self):
        self.slow.status = "under_repair"
        second_test = self.new_test()
        self.testing_task(self.test, self.tester)
        self.testing_task(second_test, self.other_tester)
        booking = self.schedule(self.test, self.tester)
        self.schedule(second_test, self.other_tester)
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        with self.assertRaises(UserError):
            event.write({"start": MONDAY + SLOT, "stop": MONDAY + 4 * SLOT})
        later = MONDAY + timedelta(hours=2)
        event.write({"start": later, "stop": later + timedelta(hours=1)})
        self.assertEqual((booking.starts_at, booking.ends_at), (later, later + 3 * SLOT))
        self.assertEqual(event.stop, later + 3 * SLOT)

    def test_the_person_running_a_test_moves_their_booking_from_its_form_and_the_calendar(self):
        self.slow.status = "under_repair"
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        waiting = self.queue(self.new_test(MONDAY + timedelta(minutes=50)), self.other_tester, MONDAY)
        self.env[MODEL_MACHINE_BOOKING]._process_queue()
        own = booking.with_user(self.tester.user_id)
        for view_type in ("form", "calendar"):
            self.assertNotIn('edit="False"', own.get_view(view_type=view_type)["arch"])

        later = MONDAY + timedelta(hours=2)
        own.write({"starts_at": later, "ends_at": later + SLOT})

        self.assertEqual((booking.starts_at, booking.ends_at), (later, later + 3 * SLOT))
        self.assertEqual((waiting.status, waiting.starts_at), ("scheduled", MONDAY))
        with self.assertRaises(AccessError):
            own.write({"person_id": self.other_tester.id})
        own.action_start()
        with self.assertRaisesRegex(UserError, "Only a scheduled booking can be moved"):
            own.write({"starts_at": MONDAY + timedelta(hours=4)})

    def test_only_the_person_running_a_test_and_their_head_adjust_its_booking(self):
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        with self.assertRaises(AccessError):
            booking.with_user(self.other_tester.user_id).action_cancel()
        booking.with_user(self.head.user_id).write({"starts_at": MONDAY + timedelta(hours=1)})
        self.assertEqual(booking.starts_at, MONDAY + timedelta(hours=1))
        booking.with_user(self.head.user_id).action_cancel()
        self.assertEqual(booking.status, "cancelled")

    def test_an_earlier_calibration_date_sends_the_bookings_after_it_to_another_machine(self):
        self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        self.fast.service_ids = [
            Command.create({"kind": "calibration", "service_date": "2025-10-10", "next_due_date": "2026-10-10"})
        ]
        self.assertEqual((booking.machine_id, booking.status), (self.slow, "scheduled"))
