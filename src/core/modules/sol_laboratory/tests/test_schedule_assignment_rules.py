from datetime import timedelta

from freezegun import freeze_time

from odoo.tests import tagged

from .location_case import LocationCase
from .schedule_invariants_case import WEEKDAYS, ScheduleInvariantsCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK_REASSIGN, MODEL_TESTING_METHOD_STEP

SLOT = timedelta(minutes=15)
AFTERNOON = MONDAY + timedelta(hours=5)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleAssignmentRules(ScheduleInvariantsCase, LocationCase):
    def test_a_reassigned_booking_moves_into_the_new_assignees_working_time_with_its_calendar_and_rooms(self):
        self.env[MODEL_TESTING_METHOD_STEP].create(
            {
                "method_id": self.method.id,
                "sequence": 1,
                "duration_minutes": 20,
                "instruction": "Prepare the sample",
                "location_id": self.room.id,
            }
        )
        self.other_tester.resource_calendar_id = self.create_calendar(
            "Afternoons in UTC", [(day, 13, 17) for day in WEEKDAYS]
        )
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        old_event, old_rooms = booking.calendar_event_id, booking.room_event_ids
        self.assertEqual((booking.starts_at, old_rooms.start), (MONDAY, MONDAY))
        self.assert_schedule_invariants(self.test)

        wizard = self.as_person(self.env[MODEL_TASK_REASSIGN], self.head).with_context(active_ids=task.ids)
        wizard.create(
            {"department_id": self.department.id, "assignee_id": self.other_tester.id, "reason": "On leave"}
        ).action_confirm()

        self.assertEqual((task.status, task.assignee_id), ("assigned", self.other_tester))
        self.assertEqual((booking.status, booking.person_id), ("scheduled", self.other_tester))
        self.assertEqual((booking.starts_at, booking.ends_at), (AFTERNOON, AFTERNOON + 3 * SLOT))
        self.assertFalse(old_event.exists())
        self.assertFalse(old_rooms.exists())
        event, rooms = booking.calendar_event_id, booking.room_event_ids
        self.assertEqual(event.user_id, self.other_tester.user_id)
        self.assertEqual((event.start, event.stop), (AFTERNOON, AFTERNOON + 3 * SLOT))
        self.assertEqual(
            (rooms.location_id, rooms.start, rooms.user_id), (self.room, AFTERNOON, self.other_tester.user_id)
        )
        self.assertEqual((task.planned_start, task.planned_end), (AFTERNOON, AFTERNOON + 3 * SLOT))
        self.assertEqual(self.test.status, "assigned")
        self.assert_schedule_invariants(self.test)
