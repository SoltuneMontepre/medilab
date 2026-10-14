from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY

REASON = "The sample matrix interferes with the method."


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestSampleTestCancellation(ResultCase):
    def cancel(self, test, person=None, reason=REASON):
        self.as_person(test, person or self.head).action_cancel(reason)

    def test_cancelling_without_a_reason_is_refused(self):
        with self.assertRaises(UserError):
            self.cancel(self.test, reason=" ")

        self.assertEqual(self.test.status, "waiting")

    def test_cancelling_cancels_the_task_and_running_booking_and_keeps_the_reason_on_the_request(self):
        booking = self.schedule(self.test, self.tester)
        self.as_person(booking, self.tester).action_start()

        self.cancel(self.test)

        self.assertEqual(self.test.status, "cancelled")
        self.assertEqual(self.test.cancel_reason, REASON)
        self.assertEqual(self.test.cancelled_by_id, self.head)
        self.assertEqual(self.task.status, "cancelled")
        self.assertEqual(booking.status, "cancelled")
        self.assertEqual(self.request.cancelled_test_ids, self.test)

    def test_only_the_department_testing_it_cancels_a_test(self):
        outsider = self.create_person(
            "Vo Thi Hoa", self.microbiology, "hoa.vo", permissions=("sample_test.read.all", "sample_test.edit.all")
        )

        with self.assertRaises(UserError):
            self.cancel(self.test, outsider)
        with self.assertRaises(AccessError):
            self.cancel(self.test, self.tester)

    def test_a_draft_result_of_a_cancelled_test_cannot_be_sent(self):
        result = self.enter()
        self.cancel(self.test)

        with self.assertRaises(UserError):
            self.send(result)
        self.assertEqual(self.test.status, "cancelled")

    def test_a_test_with_an_approved_result_cannot_be_cancelled(self):
        result = self.enter()
        self.send(result)
        self.approve(result)

        with self.assertRaises(UserError):
            self.cancel(self.test)

    def test_a_sample_whose_remaining_tests_are_approved_is_completed(self):
        arsenic = self.add_test()
        result = self.enter()
        self.send(result)
        self.approve(result)

        self.cancel(arsenic)

        self.assertEqual(self.sample.status, "completed")
        self.assertEqual(self.request.status, "completed")
