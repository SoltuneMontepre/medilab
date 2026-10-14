from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .result_case import ResultCase
from .scheduling_case import MONDAY


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestTestResultEntry(ResultCase):
    def test_a_booked_result_takes_the_booking_machine_and_start_and_can_correct_them(self):
        booking = self.schedule(self.test, self.tester)

        result = self.enter()

        self.assertEqual(result.machine_id, booking.machine_id)
        self.assertEqual(result.started_at, booking.starts_at)
        self.assertEqual(booking.status, "done")
        result.write({"machine_id": self.slow.id, "started_at": MONDAY})
        self.assertEqual(result.machine_id, self.slow)
        self.assertEqual(result.started_at, MONDAY)

    def test_a_result_copies_the_regulation_limit_and_keeps_it(self):
        result = self.enter()

        self.assertTrue(result.limit_max_set)
        self.assertFalse(result.limit_min_set)
        self.assertEqual(result.limit_max, 0.01)
        self.assertEqual(result.limit_unit_id, self.unit)
        self.limit.max_value = 0.05
        result.invalidate_recordset()
        self.assertEqual(result.limit_max, 0.01)

    def test_a_result_on_a_sample_with_a_regulation_needs_a_conclusion_before_it_is_sent(self):
        result = self.enter(conclusion=False)

        with self.assertRaises(UserError):
            self.send(result)
        result.conclusion = "fail"
        self.send(result)
        self.assertEqual(result.status, "requested")
        self.assertEqual(self.test.status, "result_entered")

    def test_a_numeric_result_keeps_the_exact_value(self):
        result = self.enter(value=0.1)
        result.flush_recordset()

        self.env.cr.execute("SELECT value::text, (value * 3)::text FROM medilab_test_result WHERE id = %s", [result.id])
        self.assertEqual(self.env.cr.fetchone(), ("0.1", "0.3"))

    def test_a_value_shows_the_decimals_of_its_way_of_testing(self):
        result = self.enter(value=0.01)

        self.assertEqual(result.unit_id, self.unit)
        self.assertEqual(result.value_decimals, 3)
        self.assertEqual(result.value_display, "0.010")

    def test_correcting_the_decimals_keeps_the_unit_of_the_way_of_testing(self):
        result = self.enter(value=0.0125, value_decimals=2)

        self.assertEqual(result.unit_id, self.unit)
        self.assertEqual(result.value_display, "0.01")

    def test_a_text_result_shows_its_text(self):
        result = self.enter(value_text="Not detected")

        self.assertEqual(result.value_display, "Not detected")

    def test_a_retest_adds_a_reported_result_and_keeps_the_earlier_one(self):
        first = self.enter()
        second = self.enter(value=0.009)

        self.assertEqual((first.attempt, second.attempt), (1, 2))
        self.assertFalse(first.is_reported)
        self.assertTrue(second.is_reported)
        with self.assertRaises(UserError):
            self.send(first)

    def test_entering_a_result_starts_the_test_its_sample_and_request(self):
        self.enter()

        self.assertEqual(self.test.status, "testing")
        self.assertEqual(self.sample.status, "testing")
        self.assertEqual(self.request.status, "testing")

    def test_a_signed_result_cannot_be_changed(self):
        result = self.enter()
        self.send(result)

        with self.assertRaises(UserError):
            self.as_person(result, self.tester).write({"value": 0.002})

    def test_no_result_is_entered_while_one_waits_for_approval(self):
        self.send(self.enter())

        with self.assertRaises(UserError):
            self.enter()

    def test_no_result_is_entered_for_a_sample_not_received(self):
        with self.assertRaises(UserError):
            self.enter(test=self.new_test())

    def test_the_system_sets_the_status_and_who_entered_the_result(self):
        result = self.enter(status="approved", entered_by_id=self.head.user_id.id)

        self.assertEqual(result.status, "none")
        self.assertEqual(result.entered_by_id, self.tester.user_id)
        with self.assertRaises(UserError):
            self.as_person(result, self.tester).write({"status": "approved"})

    def test_a_result_cannot_be_deleted(self):
        result = self.enter()

        with self.assertRaises(AccessError):
            result.with_user(self.env.ref("base.user_admin")).unlink()
