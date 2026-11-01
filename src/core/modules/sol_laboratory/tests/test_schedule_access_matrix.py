from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .cross_department_case import CrossDepartmentCase
from .scheduling_case import MONDAY

SLOT = timedelta(minutes=15)
MOVED_TO = MONDAY + timedelta(hours=6)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestScheduleAccessMatrix(CrossDepartmentCase):
    def test_only_the_head_of_the_bookings_department_moves_or_cancels_someone_elses_booking(self):
        actors = {
            "tester of the same department": (self.other_tester, False),
            "head of the department": (self.head, True),
            "head of another department": (self.microbiology_head, False),
        }
        for actor, (person, allowed) in actors.items():
            for action in ("move", "cancel"):
                with self.subTest(actor=actor, action=action), self.rolled_back():
                    task = self.testing_task(self.test, self.tester)
                    booking = self.schedule(self.test, self.tester)
                    self.assertEqual((booking.status, booking.starts_at), ("scheduled", MONDAY))
                    as_actor = booking.with_user(person.user_id)
                    act = (
                        (lambda as_actor=as_actor: as_actor.write({"starts_at": MOVED_TO}))
                        if action == "move"
                        else as_actor.action_cancel
                    )
                    if not allowed:
                        before = self.graph(self.test)
                        with self.assertRaises(AccessError), self.rolled_back():
                            act()
                        self.assertEqual(self.graph(self.test), before)
                    else:
                        act()
                        if action == "move":
                            self.assertEqual((booking.starts_at, booking.ends_at), (MOVED_TO, MOVED_TO + 3 * SLOT))
                            self.assertEqual((task.planned_start, task.planned_end), (MOVED_TO, MOVED_TO + 3 * SLOT))
                        else:
                            self.assertEqual(booking.status, "cancelled")
                            self.assertFalse(booking.calendar_event_id)
                            self.assertEqual((self.test.status, task.status), ("assigned", "assigned"))
                        self.assertEqual(booking.person_id, self.tester)
                    self.assert_schedule_invariants(self.test)
