from datetime import datetime

from odoo import fields

from .people_case import PeopleCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_SAMPLE_HANDOVER,
    MODEL_TASK,
)
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
        cls.env[MODEL_MACHINE_METHOD].create(
            [
                {"method_id": cls.pair.method_id.id, "machine_id": cls.fast.id, "duration_minutes": 40},
                {"method_id": cls.pair.method_id.id, "machine_id": cls.slow.id, "duration_minutes": 70},
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
        cls.authorize(cls.tester | cls.other_tester | cls.head, cls.parameter)
        cls.test = cls.sample.test_ids

    @classmethod
    def authorize(cls, people, parameter):
        """The Lab Head authorizes the people to test the parameter, unless they are already."""
        authorizations = cls.env[MODEL_PARAMETER_AUTHORIZATION]
        authorized = authorizations.search([("parameter_id", "=", parameter.id)]).person_id
        authorizations.create(
            [{"person_id": person.id, "parameter_id": parameter.id} for person in people - authorized]
        )

    @classmethod
    def receive(cls, sample, department):
        """The sample is received and handed over to the department, which received it."""
        if sample.status == "expected":
            sample.status = "received"
        handovers = cls.env[MODEL_SAMPLE_HANDOVER]
        handover = handovers.search([("sample_id", "=", sample.id), ("department_id", "=", department.id)])
        if not handover:
            handover = handovers.create({"sample_id": sample.id, "department_id": department.id})
        if not handover.received_at:
            handover.received_at = fields.Datetime.now()

    @classmethod
    def new_test(cls, due_date=None):
        """A lead test on a new sample."""
        test = cls.create_request().sample_ids.test_ids
        if due_date:
            test.due_date = due_date
        return test

    @classmethod
    def testing_task(cls, test, assignee=None, department=None):
        """The testing task a received sample gives the test, assigned to the person when one is given, who is authorized
        for its parameter; the department has received the sample."""
        cls.receive(test.sample_id, department or cls.department)
        task = cls.env[MODEL_TASK]._create_for_event(
            SAMPLE_RECEIVED_TRIGGER, document=test, department=department or cls.department, deadline=test.due_date
        )
        if assignee:
            cls.authorize(assignee, test.parameter_id)
            task.write({"assignee_id": assignee.id, "status": "assigned"})
        return task

    @staticmethod
    def schedule(test, person):
        test.with_user(person.user_id).action_schedule()
        return test.booking_ids.filtered(lambda booking: booking.status != "cancelled")
