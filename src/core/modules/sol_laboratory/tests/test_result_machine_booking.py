from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestResultMachineBooking(ResultCase):
    def test_the_tester_books_a_free_machine_for_a_draft_result_without_one(self):
        result = self.as_person(self.enter(), self.tester)
        self.assertTrue(result.can_book_machine)
        self.assertEqual(result.available_machine_ids, self.fast | self.slow)

        result._book_machine(self.slow)

        booking = result.booking_id
        self.assertEqual(result.machine_id, self.slow)
        self.assertEqual(
            (booking.machine_id, booking.person_id, booking.status, booking.starts_at, booking.ends_at),
            (self.slow, self.tester, "done", MONDAY, MONDAY + timedelta(minutes=75)),
        )
        self.assertEqual(result.started_at, MONDAY)
        self.assertFalse(result.can_book_machine)

    def test_a_machine_another_booking_holds_at_the_result_start_is_not_offered(self):
        result = self.as_person(self.enter(started_at=MONDAY + timedelta(hours=1)), self.tester)
        self.env[MODEL_MACHINE_BOOKING].create(
            {
                "machine_id": self.fast.id,
                "sample_test_id": self.add_test().id,
                "starts_at": MONDAY + timedelta(minutes=30),
                "ends_at": MONDAY + timedelta(minutes=90),
                "status": "scheduled",
            }
        )

        self.assertEqual(result.available_machine_ids, self.slow)
        with self.assertRaises(UserError):
            result._book_machine(self.fast)

    def test_only_the_tester_who_entered_a_draft_result_books_a_machine(self):
        result = self.enter()

        self.assertFalse(self.as_person(result, self.other_tester).can_book_machine)
        with self.assertRaises(UserError):
            self.as_person(result, self.other_tester)._book_machine(self.fast)
        self.send(result)
        with self.assertRaises(UserError):
            self.as_person(result, self.tester)._book_machine(self.fast)

    def test_a_result_with_a_booked_machine_cannot_book_another(self):
        self.schedule(self.test, self.tester)

        result = self.as_person(self.enter(), self.tester)

        self.assertTrue(result.machine_id)
        self.assertFalse(result.can_book_machine)
