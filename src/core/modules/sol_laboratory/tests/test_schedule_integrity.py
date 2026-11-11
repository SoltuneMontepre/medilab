from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .location_case import LocationCase
from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CALENDAR_EVENT, MODEL_TASK, MODEL_TESTING_METHOD_STEP


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleIntegrity(SchedulingCase, LocationCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.step = cls.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": cls.method.id,
                "sequence": 1,
                "duration_minutes": 20,
                "instruction": "Prepare the sample",
                "location_id": cls.room.id,
            }
        )

    def scheduled(self):
        self.testing_task(self.test, self.tester)
        return self.schedule(self.test, self.tester)

    @staticmethod
    def graph(booking):
        return {
            "booking": booking.read(["status", "starts_at", "ends_at", "calendar_event_id", "room_event_ids"]),
            "test": booking.sample_test_id.read(["status", "parameter_method_id", "outsourcing_suggested"]),
            "task": booking.task_id.read(["status", "assignee_id", "planned_start", "planned_end"]),
            "events": (booking.calendar_event_id | booking.room_event_ids)
            .sorted("id")
            .read(
                [
                    "start",
                    "stop",
                    "active",
                    "allday",
                    "user_id",
                    "partner_ids",
                    "alarm_ids",
                    "location_id",
                    "machine_booking_id",
                    "step_id",
                ]
            ),
        }

    def assert_refused_unchanged(self, booking, action, message="Move or cancel the machine booking"):
        before = self.graph(booking)
        with self.assertRaisesRegex(UserError, message), self.env.cr.savepoint():
            action()
        self.assertEqual(self.graph(booking), before)

    def test_boolean_sync_context_cannot_move_a_room_reservation(self):
        booking = self.scheduled()
        room = booking.room_event_ids.with_user(self.tester.user_id).with_context(medilab_skip_calendar_sync=True)
        self.assert_refused_unchanged(
            booking,
            lambda: room.write({"start": MONDAY + timedelta(hours=2), "stop": MONDAY + timedelta(hours=3)}),
        )

    def test_boolean_sync_context_cannot_delete_a_room_reservation(self):
        booking = self.scheduled()
        room = booking.room_event_ids.with_user(self.tester.user_id).with_context(medilab_skip_calendar_sync=True)
        self.assert_refused_unchanged(booking, room.unlink)

    def test_a_room_reservation_cannot_be_detached(self):
        booking = self.scheduled()
        room = booking.room_event_ids.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, lambda: room.write({"machine_booking_id": False}), "Calendar links")

    def test_a_room_reservation_cannot_change_its_step(self):
        booking = self.scheduled()
        room = booking.room_event_ids.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, lambda: room.write({"step_id": False}), "Calendar links")

    def test_a_room_reservation_cannot_change_its_attendees(self):
        booking = self.scheduled()
        room = booking.room_event_ids.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, lambda: room.write({"partner_ids": [Command.clear()]}))

    def test_the_main_calendar_event_cannot_be_deleted_independently(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, event.unlink)

    def test_the_main_calendar_event_cannot_be_archived_independently(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, event.action_archive)

    def test_false_boolean_aliases_cannot_archive_a_room_reservation(self):
        booking = self.scheduled()
        event = booking.room_event_ids.with_user(self.tester.user_id)
        for inactive in (False, 0, None):
            with self.subTest(inactive=repr(inactive)):
                self.assert_refused_unchanged(booking, lambda: event.write({"active": inactive}))

    def test_false_boolean_aliases_cannot_archive_the_main_calendar_event(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        for inactive in (False, 0, None):
            with self.subTest(inactive=repr(inactive)):
                self.assert_refused_unchanged(booking, lambda: event.write({"active": inactive}))

    def test_boolean_sync_context_cannot_desynchronize_the_main_calendar(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id).with_context(medilab_skip_calendar_sync=True)
        later = MONDAY + timedelta(hours=2)
        event.write({"start": later, "stop": later + timedelta(hours=1)})
        self.assertEqual((booking.starts_at, booking.ends_at), (later, later + timedelta(minutes=45)))
        self.assertEqual((event.start, event.stop), (booking.starts_at, booking.ends_at))
        self.assertEqual(booking.room_event_ids.start, later)
        self.assertEqual(booking.task_id.planned_start, later)

    def test_boolean_sync_context_cannot_desynchronize_a_planned_task(self):
        task = self.env[MODEL_TASK].create(
            {
                "type_id": self.env.ref("sol_laboratory.task_type_general").id,
                "name": "Check the balance",
                "department_id": self.department.id,
                "assignee_id": self.tester.id,
                "planned_start": MONDAY,
                "planned_end": MONDAY + timedelta(hours=1),
            }
        )
        later = MONDAY + timedelta(hours=2)
        task.with_user(self.head.user_id).with_context(medilab_skip_calendar_sync=True).write(
            {"planned_start": later, "planned_end": later + timedelta(hours=1)}
        )
        event = self.env[MODEL_CALENDAR_EVENT].search([("medilab_task_id", "=", task.id)])
        self.assertEqual(len(event), 1)
        self.assertEqual((event.start, event.stop), (task.planned_start, task.planned_end))
        event.with_user(self.head.user_id).write({"start": MONDAY, "stop": MONDAY + timedelta(hours=1)})
        self.assertEqual((task.planned_start, task.planned_end), (MONDAY, MONDAY + timedelta(hours=1)))

    def test_boolean_scheduling_context_cannot_bypass_a_free_slot_check(self):
        booking = self.scheduled()
        head = booking.with_user(self.head.user_id).with_context(medilab_scheduling=True)
        outside_work = MONDAY + timedelta(hours=10)
        self.assert_refused_unchanged(
            booking,
            lambda: head.write({"starts_at": outside_work, "ends_at": outside_work + timedelta(minutes=45)}),
            "is not free",
        )

    def test_a_person_cannot_create_an_event_attached_to_a_machine_booking(self):
        booking = self.scheduled()
        events = self.env[MODEL_CALENDAR_EVENT].with_user(self.tester.user_id)
        before = self.graph(booking)
        with self.assertRaisesRegex(UserError, "Calendar links"), self.env.cr.savepoint():
            events.with_context(medilab_skip_calendar_sync=True).create(
                {
                    "name": "Extra reservation",
                    "start": MONDAY + timedelta(hours=2),
                    "stop": MONDAY + timedelta(hours=3),
                    "machine_booking_id": booking.id,
                    "step_id": self.step.id,
                }
            )
        self.assertEqual(self.graph(booking), before)

    def test_a_context_default_cannot_attach_an_extra_reservation(self):
        booking = self.scheduled()
        events = self.env[MODEL_CALENDAR_EVENT].with_user(self.tester.user_id)
        before = self.graph(booking)
        with self.assertRaisesRegex(UserError, "Calendar links"), self.env.cr.savepoint():
            events.with_context(default_machine_booking_id=booking.id).create(
                {"name": "Extra reservation", "start": MONDAY, "stop": MONDAY + timedelta(hours=1)}
            )
        self.assertEqual(self.graph(booking), before)

    def test_the_main_calendar_attendees_cannot_diverge_from_the_booking(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        self.assert_refused_unchanged(booking, lambda: event.write({"partner_ids": [Command.clear()]}))

    def test_the_main_event_duration_cannot_change_the_run_length(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        event.write({"duration": 2})
        self.assertEqual((event.start, event.stop), (booking.starts_at, booking.ends_at))
        self.assertEqual(booking.ends_at - booking.starts_at, timedelta(minutes=45))

    def test_the_main_calendar_event_keeps_a_timed_booking(self):
        booking = self.scheduled()
        event = booking.calendar_event_id.with_user(self.tester.user_id)
        event.write({"allday": True})
        self.assertFalse(event.allday)
        self.assertFalse(booking.room_event_ids.allday)
        self.assertEqual((event.start, event.stop), (booking.starts_at, booking.ends_at))
        self.assertEqual(booking.ends_at - booking.starts_at, timedelta(minutes=45))

    def test_a_room_conflict_leaves_every_reservation_unchanged_then_a_valid_move_succeeds(self):
        booking = self.scheduled()
        self.book(self.room, MONDAY + timedelta(hours=2))
        own = booking.with_user(self.tester.user_id)
        self.assert_refused_unchanged(
            booking, lambda: own.write({"starts_at": MONDAY + timedelta(hours=2)}), "is not free"
        )
        later = MONDAY + timedelta(hours=4)
        own.write({"starts_at": later})
        self.assertEqual(booking.starts_at, later)
        self.assertEqual(booking.room_event_ids.start, later)
        self.assertEqual(booking.calendar_event_id.start, later)
        self.assertEqual(booking.task_id.planned_start, later)

    def test_clearing_the_start_is_refused_without_releasing_reservations(self):
        booking = self.scheduled()
        self.assert_refused_unchanged(
            booking,
            lambda: booking.with_user(self.tester.user_id).write({"starts_at": False}),
            "Cancel the booking instead of clearing its start",
        )

    def test_a_cancelled_booking_cannot_be_moved_or_cancelled_again(self):
        booking = self.scheduled()
        own = booking.with_user(self.tester.user_id)
        events = booking.calendar_event_id | booking.room_event_ids
        own.action_cancel()
        self.assertFalse(events.exists())
        self.assertFalse(booking.task_id.planned_start)
        self.assertFalse(booking.task_id.planned_end)
        self.assert_refused_unchanged(
            booking,
            lambda: own.write({"starts_at": MONDAY + timedelta(hours=2)}),
            "Only a scheduled booking can be moved",
        )
        self.assert_refused_unchanged(booking, own.action_cancel, "Only a queued or scheduled booking can be cancelled")

    def test_a_running_booking_cannot_be_moved_or_cancelled(self):
        booking = self.scheduled()
        own = booking.with_user(self.tester.user_id)
        own.action_start()
        self.assert_refused_unchanged(
            booking,
            lambda: own.write({"starts_at": MONDAY + timedelta(hours=2)}),
            "Only a scheduled booking can be moved",
        )
        self.assert_refused_unchanged(booking, own.action_cancel, "Only a queued or scheduled booking can be cancelled")
