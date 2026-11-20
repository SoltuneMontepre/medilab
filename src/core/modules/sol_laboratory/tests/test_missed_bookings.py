from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.jobs import MACHINE_BOOKINGS_MISSED_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_SCHEDULED_JOB

MISSED_EVENT = "sol_laboratory.event_machine_booking_missed"
HOUR = timedelta(hours=1)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestMissedBookings(ResultCase):
    """The tester's lead test is booked on AAS 1 from 08:00 to 08:40; AAS 2 is under repair."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.slow.status = "under_repair"

    def booking(self):
        return self.schedule(self.test, self.tester)

    def test_a_scheduled_booking_is_missed_once_its_start_passes(self):
        booking = self.booking()
        self.assertFalse(booking.is_missed)

        with freeze_time(MONDAY + timedelta(minutes=15)):
            booking.invalidate_recordset(["is_missed"])
            self.assertTrue(booking.is_missed)
            self.assertEqual(self.env[MODEL_MACHINE_BOOKING].search([("is_missed", "=", True)]), booking)

            booking.with_user(self.tester.user_id).action_start()
            booking.invalidate_recordset(["is_missed"])
            self.assertFalse(booking.is_missed)

    def test_the_tester_reschedules_a_missed_booking_to_the_next_free_slot(self):
        booking = self.booking()
        length = booking.ends_at - booking.starts_at

        with freeze_time(MONDAY + HOUR):
            booking.with_user(self.tester.user_id).action_reschedule()

            self.assertEqual((booking.status, booking.starts_at), ("scheduled", MONDAY + HOUR))
            self.assertEqual(booking.ends_at - booking.starts_at, length)
            # The tester moved it, so a plan revision may still move it.
            self.assertFalse(booking.is_pinned)
            self.assertEqual(booking.calendar_event_id.start, MONDAY + HOUR)
            booking.invalidate_recordset(["is_missed"])
            self.assertFalse(booking.is_missed)

    def test_a_rescheduled_booking_goes_after_the_bookings_that_hold_the_machine(self):
        booking = self.booking()
        other = self.add_test()
        later = self.schedule(other, self.tester)
        self.assertEqual(later.starts_at, booking.ends_at)

        with freeze_time(MONDAY + HOUR):
            booking.with_user(self.tester.user_id).action_reschedule()

            self.assertEqual(booking.starts_at, later.ends_at)

    def test_a_booking_that_has_not_missed_its_start_is_not_rescheduled(self):
        booking = self.booking()

        with self.assertRaisesRegex(UserError, "start has passed"):
            booking.with_user(self.tester.user_id).action_reschedule()

        with freeze_time(MONDAY + HOUR):
            booking.with_user(self.tester.user_id).action_start()
            with self.assertRaisesRegex(UserError, "start has passed"):
                booking.with_user(self.tester.user_id).action_reschedule()

    def test_only_the_tester_or_the_head_reschedules_a_missed_booking(self):
        booking = self.booking()

        with freeze_time(MONDAY + HOUR):
            with self.assertRaises(UserError), self.env.cr.savepoint():
                booking.with_user(self.other_tester.user_id).action_reschedule()
            self.assertEqual(booking.starts_at, MONDAY)

            booking.with_user(self.head.user_id).action_reschedule()
            self.assertEqual(booking.starts_at, MONDAY + HOUR)
            self.assertTrue(booking.is_pinned)

    def test_the_tester_and_head_are_told_once_when_a_start_is_missed(self):
        self.department.manager_id = self.head.employee_id
        (self.tester | self.head).user_id.partner_id.email = "lab@anphu.example"
        booking = self.booking()

        with freeze_time(MONDAY - HOUR):
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_MISSED_JOB)
        with freeze_time(MONDAY + HOUR):
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_MISSED_JOB)
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_MISSED_JOB)

        message = self.env["mail.message"].search(
            [
                ("model", "=", MODEL_MACHINE_BOOKING),
                ("res_id", "=", booking.id),
                ("subtype_id", "=", self.env.ref(MISSED_EVENT).id),
            ]
        )
        self.assertEqual(len(message), 1)
        self.assertIn(self.tester.user_id.partner_id, message.notification_ids.res_partner_id)
        self.assertIn(self.head.user_id.partner_id, message.notification_ids.res_partner_id)

    def test_a_started_booking_is_not_a_missed_one(self):
        booking = self.booking()
        booking.with_user(self.tester.user_id).action_start()

        with freeze_time(MONDAY + HOUR):
            self.env[MODEL_SCHEDULED_JOB]._run_key(MACHINE_BOOKINGS_MISSED_JOB)

        self.assertFalse(
            self.env["mail.message"].search(
                [
                    ("model", "=", MODEL_MACHINE_BOOKING),
                    ("res_id", "=", booking.id),
                    ("subtype_id", "=", self.env.ref(MISSED_EVENT).id),
                ]
            )
        )
