from datetime import datetime, timedelta

from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .assertions import assert_instance
from .location_case import LocationCase
from .schedule_invariants_case import ScheduleInvariantsCase
from .scheduling_case import MONDAY, calibrated
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_REQUEST,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)

SLOT = timedelta(minutes=15)
LOAD = timedelta(hours=4)


# A booking at the start of the working day must not start at the frozen time, or nobody could join it.
@freeze_time(MONDAY - timedelta(minutes=5))
@tagged("post_install", "-at_install")
class TestSharedIntervals(ScheduleInvariantsCase, LocationCase):
    """ICP-MS 1 measures lead, cadmium and arsenic by the case's method in 4-hour loads of up to 20 samples; the AAS
    machines are under repair."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.fast | cls.slow).write({"status": "under_repair"})
        cls.icp_ms = cls.env[MODEL_MACHINE].create(calibrated({"code": "ICPMS-1", "name": "ICP-MS 1"}))
        cls.metals = cls.env[MODEL_MACHINE_METHOD].create(
            {"machine_id": cls.icp_ms.id, "method_id": cls.method.id, "duration_minutes": 240, "capacity": 20}
        )
        cls.cadmium = cls.create_parameter("Cadmium (Cd)", cls.group)
        cls.arsenic = cls.create_parameter("Arsenic (As)", cls.group)
        for parameter in (cls.cadmium, cls.arsenic):
            cls.offer(parameter, cls.sample_type)

    @classmethod
    def samples(cls, count):
        """A request of bottled water samples, each tested for lead, cadmium and arsenic."""
        request = cls.env[MODEL_TEST_REQUEST].create(
            {
                "customer_id": cls.customer.id,
                "expected_date": "2026-10-20",
                "sample_ids": [
                    Command.create(
                        {
                            "customer_sample_name": f"Well water {number}",
                            "sample_type_id": cls.sample_type.id,
                            "physical_state": "liquid",
                            "test_ids": [
                                Command.create({"parameter_id": parameter.id})
                                for parameter in (cls.parameter, cls.cadmium, cls.arsenic)
                            ],
                        }
                    )
                    for number in range(count)
                ],
            }
        )
        return request.sample_ids

    def lead(self, samples):
        return samples.test_ids.filtered(lambda test: test.parameter_id == self.parameter)

    def queue(self, tests):
        """Queue a booking of each test for the tester, then give the queue its slots."""
        bookings = self.env[MODEL_MACHINE_BOOKING].create(
            [{"sample_test_id": test.id, "person_id": self.tester.id} for test in tests]
        )
        bookings._process_queue()
        return bookings

    def interval(self, bookings):
        return set(zip(bookings.mapped("machine_id"), bookings.mapped("starts_at"), bookings.mapped("ends_at")))

    def test_the_icp_ms_example_shares_one_interval_among_60_bookings_of_20_samples(self):
        samples = self.samples(21)

        load = self.queue(samples[:20].test_ids)

        self.assertEqual(len(load), 60)
        self.assertEqual(set(load.mapped("status")), {"scheduled"})
        self.assertEqual(self.interval(load), {(self.icp_ms, MONDAY, MONDAY + LOAD)})
        self.assertEqual(len(load.sample_test_id.sample_id), 20)
        self.assertEqual(set(load.mapped("method_id")), {self.method})

        waiting = self.queue(samples[20].test_ids)

        [(machine, start, _end)] = self.interval(waiting)
        self.assertEqual(machine, self.icp_ms)
        self.assertGreaterEqual(assert_instance(start, datetime), MONDAY + LOAD)

    def test_several_parameters_of_one_sample_take_one_place(self):
        self.metals.capacity = 1
        first, second = self.samples(2)

        load = self.queue(first.test_ids)
        waiting = self.queue(self.lead(second))

        self.assertEqual(self.interval(load), {(self.icp_ms, MONDAY, MONDAY + LOAD)})
        self.assertGreaterEqual(assert_instance(waiting.starts_at, datetime), MONDAY + LOAD)
        with self.assertRaisesRegex(ValidationError, "is full"), self.env.cr.savepoint():
            waiting._set({"starts_at": MONDAY, "ends_at": MONDAY + LOAD})

    def test_a_booking_of_another_method_waits_even_with_places_left(self):
        chromium = self.create_parameter("Chromium (VI)", self.group)
        colorimetry = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6658:2000", "name": "Chromium (VI) by colorimetry", "field_id": self.testing_field.id}
        )
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": chromium.id, "method_id": colorimetry.id, "department_id": self.department.id}
        )
        self.offer(chromium, self.sample_type, way)
        self.env[MODEL_MACHINE_METHOD].create(
            {"machine_id": self.icp_ms.id, "method_id": colorimetry.id, "duration_minutes": 240, "capacity": 20}
        )
        sample = self.samples(1)
        lead = self.queue(self.lead(sample))
        test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": sample.id, "parameter_id": chromium.id})

        booking = self.queue(test)

        self.assertEqual(lead.starts_at, MONDAY)
        self.assertEqual(booking.machine_id, self.icp_ms)
        self.assertGreaterEqual(assert_instance(booking.starts_at, datetime), assert_instance(lead.ends_at, datetime))
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            booking._set({"starts_at": lead.starts_at, "ends_at": lead.ends_at})
            self.env.flush_all()

    def test_nothing_joins_an_interval_once_it_has_started(self):
        first, second, third = self.samples(3)
        running = self.queue(self.lead(first))
        self.assertEqual(running.starts_at, MONDAY)

        with self.subTest(started="by the tester"), self.rolled_back():
            running._set({"status": "in_progress"})
            late = self.queue(self.lead(second))
            self.assertGreaterEqual(
                assert_instance(late.starts_at, datetime), assert_instance(running.ends_at, datetime)
            )

        with self.subTest(started="at its start time"), freeze_time(MONDAY + SLOT), self.rolled_back():
            late = self.queue(self.lead(third))
            self.assertGreaterEqual(
                assert_instance(late.starts_at, datetime), assert_instance(running.ends_at, datetime)
            )
            with self.assertRaisesRegex(ValidationError, "has started"), self.env.cr.savepoint():
                late._set({"starts_at": running.starts_at, "ends_at": running.ends_at})

    def test_bookings_sharing_an_interval_book_its_room_once_and_hand_it_over(self):
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": self.method.id,
                "sequence": 1,
                "duration_minutes": 30,
                "instruction": "Digest",
                "location_id": self.room.id,
            }
        )
        tests = self.lead(self.samples(2))
        for test in tests:
            self.testing_task(test, self.tester)

        holder = self.schedule(tests[0], self.tester)
        joiner = self.schedule(tests[1], self.tester)

        self.assertEqual(self.interval(holder | joiner), {(self.icp_ms, MONDAY, MONDAY + LOAD)})
        self.assertEqual(len(holder.room_event_ids), 1)
        self.assertFalse(joiner.room_event_ids)
        self.assert_schedule_invariants(tests)

        holder.with_user(self.tester.user_id).action_cancel()

        room = joiner.room_event_ids
        self.assertEqual((room.location_id, room.start, room.stop), (self.room, MONDAY, MONDAY + 2 * SLOT))
        self.assert_schedule_invariants(tests)

    def test_a_way_without_a_machine_is_booked_for_its_own_duration_once_it_has_one(self):
        sensory = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 3215-79", "name": "Sensory evaluation", "field_id": self.testing_field.id}
        )
        odour = self.create_parameter("Odour", self.group)
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": odour.id, "method_id": sensory.id, "department_id": self.department.id}
        )
        self.offer(odour, self.sample_type, way)
        test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": odour.id})
        self.testing_task(test, self.tester)
        self.assertFalse(test.recommended_start)

        way.duration_minutes = 20
        test.invalidate_recordset()
        booking = self.schedule(test, self.tester)

        self.assertEqual(
            (booking.machine_id, booking.method_id, booking.starts_at, booking.ends_at),
            (self.icp_ms.browse(), sensory, MONDAY, MONDAY + 2 * SLOT),
        )
        self.assert_schedule_invariants(test)
