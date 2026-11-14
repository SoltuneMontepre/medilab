from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .assertions import assert_instance
from .result_case import ResultCase
from .scheduling_case import MONDAY, calibrated
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_LOCATION_UNAVAILABILITY,
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_METHOD,
    MODEL_RESOURCE_CALENDAR_LEAVES,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)

RETURNED_EVENT = "sol_laboratory.event_machine_booking_returned"
INTERRUPTED_EVENT = "sol_laboratory.event_test_result_interrupted"
REASON = "The customer withdrew the parameter."


# A booking at the start of the working day must not start at the frozen time, or nobody could join it.
@freeze_time(MONDAY - timedelta(minutes=5))
@tagged("post_install", "-at_install")
class TestInterruptions(ResultCase):
    """The tester's lead test runs on AAS 1 in 40 minutes or AAS 2 in 70; the head of department heads the
    department."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.department.manager_id = cls.head.employee_id
        (cls.tester | cls.head).user_id.partner_id.email = "lab@anphu.example"

    def another_test(self, person=None):
        """A lead test on a new sample, assigned to the person."""
        test = self.new_test()
        self.testing_task(test, person or self.tester)
        return test

    def notified(self, event, record):
        """The partners notified of the event about the record."""
        messages = self.env["mail.message"].search(
            [("model", "=", record._name), ("res_id", "=", record.id), ("subtype_id", "=", self.env.ref(event).id)]
        )
        return messages.notification_ids.res_partner_id

    def fail_during_measurement(self):
        """Start the tester's lead test on AAS 1, then put AAS 1 under repair."""
        booking = self.schedule(self.test, self.tester)
        self.as_person(booking, self.tester).action_start()
        self.fast.status = "under_repair"
        return booking

    def test_leave_returns_only_the_bookings_not_started_that_it_overlaps(self):
        running = self.schedule(self.test, self.tester)
        self.as_person(running, self.tester).action_start()
        waiting = self.schedule(self.another_test(), self.tester)
        colleague = self.schedule(self.another_test(self.other_tester), self.other_tester)
        before = (colleague.status, colleague.starts_at)
        self.assertEqual(waiting.starts_at, running.ends_at)

        self.env[MODEL_RESOURCE_CALENDAR_LEAVES].create(
            {
                "name": "Annual leave",
                "resource_id": self.tester.employee_id.resource_id.id,
                "date_from": MONDAY + timedelta(minutes=30),
                "date_to": MONDAY + timedelta(hours=12),
            }
        )

        self.assertEqual((running.status, running.starts_at), ("in_progress", MONDAY))
        self.assertEqual((waiting.status, waiting.person_id), ("scheduled", self.tester))
        self.assertGreaterEqual(assert_instance(waiting.starts_at, datetime), MONDAY + timedelta(hours=12))
        self.assertEqual((colleague.status, colleague.starts_at), before)
        self.assertIn(self.head.user_id.partner_id, self.notified(RETURNED_EVENT, waiting))
        self.assertFalse(self.notified(RETURNED_EVENT, running))

    def test_an_unavailable_room_returns_the_bookings_it_overlaps_and_refuses_new_ones(self):
        hood = self.env[MODEL_LOCATION].create({"code": "HOOD-1", "name": "Fume hood 1", "is_bookable": True})
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": self.method.id,
                "sequence": 1,
                "duration_minutes": 15,
                "instruction": "Digest the sample.",
                "location_id": hood.id,
            }
        )
        booking = self.schedule(self.test, self.tester)
        self.assertEqual((booking.starts_at, booking.room_event_ids.location_id), (MONDAY, hood))

        closure = self.env[MODEL_LOCATION_UNAVAILABILITY].create(
            {
                "location_id": hood.id,
                "starts_at": MONDAY,
                "ends_at": MONDAY + timedelta(hours=2),
                "reason": "The extraction fan is replaced.",
            }
        )

        self.assertEqual(booking.status, "scheduled")
        self.assertGreaterEqual(booking.room_event_ids.start, assert_instance(closure.ends_at, datetime))
        self.assertIn(self.head.user_id.partner_id, self.notified(RETURNED_EVENT, booking))
        with self.assertRaisesRegex(ValidationError, "cannot be used"), self.env.cr.savepoint():
            self.env[MODEL_CALENDAR_EVENT].create(
                {
                    "name": "Method validation",
                    "location_id": hood.id,
                    "start": MONDAY + timedelta(hours=1),
                    "stop": MONDAY + timedelta(hours=2),
                }
            )

    def test_a_machine_failure_keeps_the_recorded_data_as_an_interrupted_result_the_head_assesses(self):
        booking = self.fail_during_measurement()

        result = self.test.result_ids
        self.assertTrue(result.is_interrupted)
        self.assertFalse(result.interruption_assessment)
        self.assertEqual((result.booking_id, result.entered_by_id), (booking, self.tester.user_id))
        self.assertEqual(booking.status, "done")
        self.assertIn(self.head.user_id.partner_id, self.notified(INTERRUPTED_EVENT, result))
        self.assertIn(self.tester.user_id.partner_id, self.notified(INTERRUPTED_EVENT, result))

        self.as_person(result, self.tester).write({"value": 0.004, "conclusion": "pass"})
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.as_person(result, self.tester).action_assess_usable()
        with self.assertRaises(UserError), self.env.cr.savepoint():
            self.as_person(result, self.tester).write({"interruption_assessment": "usable"})
        with self.assertRaisesRegex(UserError, "assesses it as usable"), self.env.cr.savepoint():
            self.send(result)

        self.as_person(result, self.head).action_assess_usable()
        self.send(result)

        self.assertEqual((result.interruption_assessment, result.status), ("usable", "requested"))

    def test_a_lost_calibration_interrupts_the_measurement(self):
        booking = self.schedule(self.test, self.tester)
        self.as_person(booking, self.tester).action_start()

        self.fast.service_ids = [
            Command.create({"kind": "calibration", "service_date": "2026-10-01", "next_due_date": "2026-10-11"})
        ]

        self.assertEqual(booking.status, "done")
        self.assertTrue(self.test.result_ids.is_interrupted)

    def test_a_retest_is_a_new_result_with_a_new_booking_on_a_machine_linked_to_the_method(self):
        booking = self.fail_during_measurement()
        interrupted = self.test.result_ids
        self.as_person(interrupted, self.head).action_assess_retest()
        # Another way of testing lead would finish sooner, on a machine of another method.
        icp_method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "SMEWW 3125B", "name": "Metals by ICP-MS", "field_id": self.testing_field.id}
        )
        icp_way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": self.parameter.id, "method_id": icp_method.id, "department_id": self.department.id}
        )
        self.offer(self.parameter, self.sample_type, way=icp_way)
        icp_ms = self.env[MODEL_MACHINE].create(calibrated({"code": "ICPMS-1", "name": "ICP-MS 1"}))
        self.env[MODEL_MACHINE_METHOD].create(
            {"machine_id": icp_ms.id, "method_id": icp_method.id, "duration_minutes": 15}
        )

        retest_booking = self.schedule(self.test, self.tester) - booking
        retest = self.enter()

        self.assertEqual((retest_booking.machine_id, retest_booking.method_id), (self.slow, self.method))
        self.assertEqual((retest.booking_id, retest.is_reported), (retest_booking, True))
        self.assertFalse(interrupted.is_reported)
        self.assertEqual(interrupted.interruption_assessment, "retest")
        stray = self.env[MODEL_MACHINE_BOOKING].create(
            {"machine_id": icp_ms.id, "sample_test_id": self.test.id, "method_id": self.method.id}
        )
        with self.assertRaisesRegex(ValidationError, "retest"), self.env.cr.savepoint():
            stray._set(
                {
                    "status": "scheduled",
                    "starts_at": MONDAY + timedelta(days=1),
                    "ends_at": MONDAY + timedelta(days=1, minutes=15),
                }
            )

    def test_cancelling_a_test_leaves_the_others_in_its_interval_unchanged(self):
        self.env[MODEL_MACHINE_METHOD].search([("machine_id", "=", self.fast.id)]).capacity = 3
        tests = self.test | self.another_test() | self.another_test()
        bookings = self.env[MODEL_MACHINE_BOOKING]
        for test in tests:
            bookings |= self.schedule(test, self.tester)
        self.assertEqual(set(bookings.mapped("starts_at")), {MONDAY})
        self.assertEqual(bookings.machine_id, self.fast)

        def shown(records):
            return [(booking.status, booking.machine_id, booking.starts_at, booking.ends_at) for booking in records]

        before = shown(bookings[1:])
        self.as_person(tests[0], self.head).action_cancel(REASON)
        self.assertEqual(bookings[0].status, "cancelled")
        self.assertEqual(shown(bookings[1:]), before)

        self.as_person(bookings[1:], self.tester).action_start()
        before = shown(bookings[2:])
        self.as_person(tests[1], self.head).action_cancel(REASON)

        self.assertEqual((tests[1].status, bookings[1].status), ("cancelled", "cancelled"))
        self.assertEqual(shown(bookings[2:]), before)
        self.assertEqual(bookings[2].status, "in_progress")
