from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command
from odoo.tests import tagged

from .location_case import LocationCase
from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_MAIL_MESSAGE,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_ids

REMIND = "notifications.remind"


@tagged("post_install", "-at_install")
class TestLocationBookings(PeopleCase, LocationCase):
    """The chemist books meeting rooms and invites the microbiologist."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.start = (fields.Datetime.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        (cls.chemist | cls.microbiologist).user_id.notification_type = "inbox"

    def book(self, location, start=None, user=None, **vals):
        attendees = (self.chemist | self.microbiologist).user_id.partner_id
        return super().book(
            location,
            start or self.start,
            user=user or self.chemist.user_id,
            partner_ids=[Command.set(persisted_ids(attendees))],
            **vals,
        )

    def test_a_booking_shows_on_the_calendars_of_its_organiser_and_attendees_and_on_the_locations_schedule(self):
        booking = self.book(self.room)

        for person in (self.chemist, self.microbiologist):
            events = self.as_person(self.env[MODEL_CALENDAR_EVENT], person)
            with self.subTest(person=person.name):
                self.assertIn(booking, events.search([("partner_ids", "in", person.user_id.partner_id.id)]))
        schedule = self.room.action_open_bookings()
        self.assertEqual(self.env[MODEL_CALENDAR_EVENT].search(schedule["domain"]), booking)
        self.assertEqual(schedule["context"], {"default_location_id": self.room.id})
        self.assertEqual((booking.user_id, booking.location), (self.chemist.user_id, "A101 Meeting room 1"))
        self.assertFalse(booking.alarm_ids)

    def test_booking_shows_the_bookings_of_the_locations_under_a_floor(self):
        bookings = self.book(self.room) | self.book(self.other_room)

        schedule = self.floor.action_open_bookings()

        self.assertEqual(self.env[MODEL_CALENDAR_EVENT].search(schedule["domain"]), bookings)
        self.assertEqual(schedule["context"], {})

    def test_booking_a_time_that_overlaps_another_booking_is_refused_naming_it(self):
        self.book(self.room, name="Quality review")
        later = self.book(self.room, self.start + timedelta(hours=2))

        for name, change in {
            "create": lambda: self.book(
                self.room, self.start + timedelta(minutes=30), user=self.microbiologist.user_id
            ),
            "move": lambda: later.write({"start": self.start, "stop": self.start + timedelta(hours=1)}),
        }.items():
            with self.subTest(change=name):
                message = self.refused_message(change, MODEL_CALENDAR_EVENT)
                self.assertIn("A101 Meeting room 1 is already booked", message)
                self.assertIn("Quality review", message)

    def test_back_to_back_bookings_other_locations_and_cancelled_bookings_do_not_overlap(self):
        first = self.book(self.room)
        self.book(self.room, self.start + timedelta(hours=1))
        self.book(self.other_room)

        first.action_archive()
        replacement = self.book(self.room, name="Moved meeting")

        self.env.flush_all()
        self.assertEqual(replacement.location_id, self.room)

    def test_a_location_that_is_not_bookable_or_is_archived_cannot_be_booked(self):
        offered = self.env[MODEL_LOCATION].search([("id", "child_of", self.building.id), ("is_bookable", "=", True)])
        self.assertEqual(offered, self.room | self.other_room)
        self.assertEqual(self.env[MODEL_CALENDAR_EVENT]._fields["location_id"].domain, "[('is_bookable', '=', True)]")
        self.other_room.action_archive()

        for location in (self.sampling_point, self.other_room):
            with self.subTest(location=location.code), self.assertRaises(ValidationError) as refusal:
                self.book(location)
            self.assertEqual(str(refusal.exception), f"{location.display_name} cannot be booked.")

    def test_the_organiser_moves_or_cancels_and_an_administrator_can_cancel_any_booking(self):
        booking = self.book(self.room)
        other = self.book(self.other_room)
        attendee = self.microbiologist.user_id
        administrator = self.env.ref("base.user_admin")
        self.assertEqual(
            [booking.with_user(user).user_can_edit for user in (self.chemist.user_id, attendee, administrator)],
            [True, False, True],
        )

        for name, change in {
            "move": lambda: booking.with_user(attendee).write({"start": self.start + timedelta(hours=3)}),
            "change the location": lambda: booking.with_user(attendee).write({"location_id": self.other_room.id}),
            "cancel": booking.with_user(attendee).action_archive,
            "delete": booking.with_user(attendee).unlink,
            "move as an administrator": lambda: booking.with_user(administrator).write(
                {"start": self.start + timedelta(hours=3), "stop": self.start + timedelta(hours=4)}
            ),
        }.items():
            with self.subTest(change=name), self.assertRaises(UserError):
                change()

        booking.write({"start": self.start + timedelta(hours=3), "stop": self.start + timedelta(hours=4)})
        self.assertEqual(booking.start, self.start + timedelta(hours=3))
        booking.with_user(administrator).action_archive()
        other.with_user(administrator).unlink()
        self.assertFalse(booking.active)
        self.assertFalse(other.exists())

    def test_an_attendee_cannot_archive_a_booking_with_false_boolean_aliases(self):
        booking = self.book(self.room)
        attendee = booking.with_user(self.microbiologist.user_id)
        snapshot_fields = ["active", "start", "stop", "location_id", "user_id", "partner_ids"]
        before = booking.read(snapshot_fields)
        for inactive in (False, 0, None):
            with self.subTest(inactive=repr(inactive)):
                with (
                    self.assertRaisesRegex(UserError, "Only the organiser or an administrator can cancel"),
                    self.env.cr.savepoint(),
                ):
                    attendee.write({"active": inactive})
                self.assertEqual(booking.read(snapshot_fields), before)

    def test_a_booking_is_reminded_once_to_its_organiser_and_attendees(self):
        booking = self.book(self.room)

        with freeze_time(self.start - timedelta(minutes=10)):
            self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)
            self.env[MODEL_SCHEDULED_JOB]._run_key(REMIND)

        message = self.env[MODEL_MAIL_MESSAGE].search(
            [("notification_key", "=like", f"calendar:{booking.id}:reminder:%")]
        )
        self.assertEqual(len(message), 1)
        self.assertEqual((message.model, message.res_id), (MODEL_CALENDAR_EVENT, booking.id))
        self.assertEqual(
            message.notification_ids.res_partner_id, (self.chemist | self.microbiologist).user_id.partner_id
        )
