from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .location_case import LocationCase
from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CALENDAR_EVENT, MODEL_TESTING_METHOD_STEP

SLOT = timedelta(minutes=15)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestStepRoomBookings(SchedulingCase, LocationCase):
    """The method weighs in a bookable preparation room, rinses at a sampling point and digests in the room again."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.weigh, cls.rinse, cls.digest = cls.env[MODEL_TESTING_METHOD_STEP].create(
            [
                {
                    "method_id": cls.method.id,
                    "sequence": 1,
                    "duration_minutes": 20,
                    "instruction": "Weigh",
                    "location_id": cls.room.id,
                },
                {
                    "method_id": cls.method.id,
                    "sequence": 2,
                    "duration_minutes": 30,
                    "instruction": "Rinse",
                    "location_id": cls.sampling_point.id,
                },
                {
                    "method_id": cls.method.id,
                    "sequence": 3,
                    "duration_minutes": 45,
                    "instruction": "Digest",
                    "location_id": cls.room.id,
                },
            ]
        )

    def scheduled(self, test=None, person=None):
        test = test or self.test
        person = person or self.tester
        self.testing_task(test, person)
        return self.schedule(test, person)

    def room_times(self, booking):
        return [(event.step_id, event.start, event.stop) for event in booking.room_event_ids.sorted("start")]

    def test_scheduling_books_the_room_of_each_step_for_the_step_time(self):
        booking = self.scheduled()
        self.assertEqual(booking.starts_at, MONDAY)
        self.assertEqual(
            self.room_times(booking),
            [(self.weigh, MONDAY, MONDAY + 2 * SLOT), (self.digest, MONDAY + 4 * SLOT, MONDAY + 7 * SLOT)],
        )
        self.assertEqual(booking.room_event_ids.location_id, self.room)

    def test_a_room_booking_shows_on_the_testers_calendar_and_the_rooms_schedule(self):
        booking = self.scheduled()
        for event in booking.room_event_ids:
            self.assertEqual(event.partner_ids, self.tester.user_id.partner_id)
            self.assertEqual(event.user_id, self.tester.user_id)
        schedule = self.env[MODEL_CALENDAR_EVENT].search(self.room.action_open_bookings()["domain"])
        self.assertEqual(booking.room_event_ids & schedule, booking.room_event_ids)

    def test_a_test_waits_until_the_machine_and_every_room_are_free(self):
        self.book(self.room, MONDAY + 4 * SLOT, hours=0.5)
        booking = self.scheduled()
        # The digestion needs the room from an hour after the start, so the test starts half an hour late.
        self.assertEqual(booking.starts_at, MONDAY + 2 * SLOT)
        self.assertEqual(self.test.parameter_method_id, self.pair)

    def test_two_tests_never_book_the_same_room_at_once(self):
        first = self.scheduled()
        second = self.scheduled(self.new_test(), self.other_tester)
        self.assertEqual(second.starts_at, MONDAY + 7 * SLOT)
        for mine in first.room_event_ids:
            for theirs in second.room_event_ids:
                self.assertFalse(mine.start < theirs.stop and theirs.start < mine.stop)

    def test_no_slot_is_found_when_a_room_step_would_end_after_the_due_date(self):
        test = self.new_test(MONDAY + timedelta(minutes=90))
        self.testing_task(test, self.tester)
        self.assertFalse(test.recommended_machine_id)
        self.assertTrue(test.outsourcing_suggested)

    def test_moving_a_booking_moves_its_room_bookings(self):
        booking = self.scheduled()
        later = MONDAY + timedelta(hours=1)
        booking.with_user(self.tester.user_id).write({"starts_at": later})
        self.assertEqual(
            self.room_times(booking),
            [(self.weigh, later, later + 2 * SLOT), (self.digest, later + 4 * SLOT, later + 7 * SLOT)],
        )

    def test_a_booking_moves_only_where_its_rooms_are_free(self):
        booking = self.scheduled()
        self.book(self.room, MONDAY + timedelta(hours=3), hours=1)
        with self.assertRaises(UserError):
            booking.with_user(self.tester.user_id).write({"starts_at": MONDAY + timedelta(hours=2)})

    def test_cancelling_a_booking_cancels_its_room_bookings(self):
        booking = self.scheduled()
        events = booking.room_event_ids
        booking.with_user(self.tester.user_id).action_cancel()
        self.assertFalse(events.exists())

    def test_a_machine_becoming_unavailable_reschedules_the_room_bookings(self):
        booking = self.scheduled()
        self.fast.status = "under_repair"
        self.assertEqual((booking.machine_id, booking.starts_at), (self.slow, MONDAY))
        self.assertEqual(len(booking.room_event_ids), 2)

    def test_a_room_booking_follows_its_machine_booking_only(self):
        event = self.scheduled().room_event_ids[:1].with_user(self.tester.user_id)
        self.assertFalse(event.user_can_edit)
        with self.assertRaises(UserError):
            event.write({"start": MONDAY + timedelta(hours=4), "stop": MONDAY + timedelta(hours=5)})
        with self.assertRaises(UserError):
            event.unlink()

    def test_a_step_that_is_not_bookable_books_nothing(self):
        self.room.is_bookable = False
        booking = self.scheduled()
        self.assertFalse(booking.room_event_ids)
