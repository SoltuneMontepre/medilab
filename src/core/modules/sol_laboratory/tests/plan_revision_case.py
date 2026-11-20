from datetime import datetime, timedelta

from .cross_department_case import CrossDepartmentCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_METHOD,
    MODEL_OVERTIME,
    MODEL_PLAN_REVISION,
)

# Tuesday 16:00 UTC, when urgent sample X arrives.
TUESDAY = datetime(2026, 10, 13, 16, 0)
# GC-01 has two 4-hour intervals on Wednesday, 08:00 to 12:00 and 12:00 to 16:00, and then Thursday morning.
WEDNESDAY = datetime(2026, 10, 14, 8, 0)
AFTERNOON = datetime(2026, 10, 14, 12, 0)
# The OverTime of the tester on Wednesday gives a third interval.
EVENING = datetime(2026, 10, 14, 17, 0)
THURSDAY = datetime(2026, 10, 15, 8, 0)
RUN = timedelta(hours=4)
# The expected return date is Friday, so the internal due date, two days before it, is the end of Wednesday.
FRIDAY = "2026-10-16"
MOVED_EVENT = "sol_laboratory.event_machine_booking_moved"


class PlanRevisionCase(CrossDepartmentCase):
    """GC-01 runs lead in 4 hours for the one tester of the chemistry department. Z holds Wednesday morning and Y
    Wednesday afternoon, both normal tests with the expected return date Friday; urgent sample X arrives on Tuesday
    at 16:00 with the same dates. Run the tests at TUESDAY."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Due dates are the end of a day in the laboratory's time zone.
        cls.env.company.tz = "UTC"
        cls.slow.status = "under_repair"
        cls.department.manager_id = cls.head.employee_id
        cls.env[MODEL_MACHINE_METHOD].search([("machine_id", "=", cls.fast.id)]).duration_minutes = 240
        cls.grant(
            cls.head,
            "overtime.read.own_department",
            "overtime.create.own_department",
            "plan_revision.read.own_department",
            "plan_revision_move.read.own_department",
        )
        (cls.tester | cls.head).user_id.partner_id.email = "lab@anphu.example"
        cls.z_test, cls.y_test = cls.committed(), cls.committed()
        cls.z, cls.y = cls.booked(cls.z_test), cls.booked(cls.y_test)

    @classmethod
    def committed(cls):
        """A lead test whose results are promised on the Friday."""
        test = cls.new_test()
        test.sample_id.request_id.committed_date = FRIDAY
        return test

    @classmethod
    def booked(cls, test, person=None):
        """The scheduled booking of the test for the tester, or for the person."""
        person = person or cls.tester
        cls.testing_task(test, person, person.department_id)
        return cls.schedule(test, person)

    def urgent_arrives(self):
        """Urgent sample X is assigned to the tester and marked urgent; yields its test and its proposed booking."""
        test = self.committed()
        self.testing_task(test, self.tester)
        test.with_user(self.tester.user_id)._mark_urgent("The customer needs it for a recall")
        return test, test.booking_ids

    def record_overtime(self):
        """The head of chemistry records OverTime for the tester on Wednesday from 17:00 to 21:00."""
        return self.as_person(self.env[MODEL_OVERTIME], self.head).create(
            {
                "person_id": self.tester.id,
                "starts_at": EVENING,
                "ends_at": EVENING + RUN,
                "reason": "Urgent lead tests would otherwise miss their due date.",
            }
        )

    def open_revision(self):
        """The one proposed revision of the department's plan."""
        revision = self.env[MODEL_PLAN_REVISION].search(
            [("department_id", "=", self.department.id), ("status", "=", "proposed")]
        )
        self.assertEqual(len(revision), 1)
        return revision

    @staticmethod
    def moves(revision):
        """What a revision holds: for each booking, the state of its move and the start it would move to."""
        return {move.booking_id: (move.status, move.starts_at) for move in revision.move_ids}
