from datetime import datetime

from .people_case import PeopleCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE, MODEL_PARAMETER_METHOD_MACHINE, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RECEIVED_TRIGGER

# A Monday at the start of the working day, in UTC.
MONDAY = datetime(2026, 10, 12, 8, 0)


class SchedulingCase(RequestCase, PeopleCase):
    """Two machines run lead in 40 and 70 minutes. Two testers and their head of department work standard hours in UTC."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fast, cls.slow = cls.env[MODEL_MACHINE].create(
            [{"code": "AAS-1", "name": "AAS 1"}, {"code": "AAS-2", "name": "AAS 2"}]
        )
        cls.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            [
                {"parameter_method_id": cls.pair.id, "machine_id": cls.fast.id, "run_minutes": 40},
                {"parameter_method_id": cls.pair.id, "machine_id": cls.slow.id, "run_minutes": 70},
            ]
        )
        cls.tester = cls.create_person(
            "Le Van Cuong", cls.department, "cuong.le", permissions=("sample_test.read.all",)
        )
        cls.other_tester = cls.create_person(
            "Pham Thi Dung", cls.department, "dung.pham", permissions=("sample_test.read.all",)
        )
        cls.head = cls.create_person(
            "Hoang Van Em",
            cls.department,
            "em.hoang",
            permissions=(
                "sample_test.read.all",
                "task.read.own_department",
                "task.edit.own_department",
                "machine_booking.read.own_department",
                "machine_booking.create.own_department",
                "machine_booking.edit.own_department",
            ),
        )
        (cls.tester | cls.other_tester | cls.head).tz = "UTC"
        cls.test = cls.sample.test_ids

    @classmethod
    def new_test(cls, due_date=None):
        """A lead test on a new sample."""
        test = cls.create_request().sample_ids.test_ids
        if due_date:
            test.due_date = due_date
        return test

    @classmethod
    def testing_task(cls, test, assignee=None, department=None):
        """The testing task a received sample gives the test, assigned to the person when one is given."""
        task = cls.env[MODEL_TASK]._create_for_event(
            SAMPLE_RECEIVED_TRIGGER, document=test, department=department or cls.department, deadline=test.due_date
        )
        if assignee:
            task.write({"assignee_id": assignee.id, "status": "assigned"})
        return task

    @staticmethod
    def schedule(test, person):
        test.with_user(person.user_id).action_schedule()
        return test.booking_ids.filtered(lambda booking: booking.status != "cancelled")
