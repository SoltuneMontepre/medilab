from freezegun import freeze_time
from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
)

LAB_HEAD_PERMISSIONS = (
    "parameter_authorization.create.all",
    "parameter_authorization.edit.all",
    "parameter_authorization.delete.all",
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestParameterAuthorization(SchedulingCase):
    """The tester, the other tester and the head may test lead; the trainee may not."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lab_head = cls.create_person("Vu Thi Thao", login="thao.vu", permissions=LAB_HEAD_PERMISSIONS)
        cls.trainee = cls.create_person("Do Van Khoa", cls.department, "khoa.do", permissions=("sample_test.read.all",))
        cls.trainee.tz = "UTC"
        cls.authorizations = cls.env[MODEL_PARAMETER_AUTHORIZATION]

    def authorization(self, person):
        return self.authorizations.search([("person_id", "=", person.id), ("parameter_id", "=", self.parameter.id)])

    def test_the_lab_head_maintains_authorizations_and_nobody_else_changes_them(self):
        added = self.as_person(self.authorizations, self.lab_head).create(
            {"person_id": self.trainee.id, "parameter_id": self.parameter.id}
        )
        self.assertEqual(self.as_person(self.authorizations, self.tester).search([]), self.authorizations.search([]))
        for person in (self.head, self.tester):
            with self.assertRaises(AccessError):
                self.as_person(self.authorizations, person).create(
                    {"person_id": self.lab_head.id, "parameter_id": self.parameter.id}
                )
            with self.assertRaises(AccessError):
                self.as_person(added, person).write({"person_id": person.id})
            with self.assertRaises(AccessError):
                self.as_person(added, person).unlink()
        self.as_person(added, self.lab_head).unlink()
        self.assertFalse(self.authorization(self.trainee))

    def test_a_person_is_authorized_once_for_a_parameter_until_they_are_deleted(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError), self.cr.savepoint():
            self.authorizations.create({"person_id": self.tester.id, "parameter_id": self.parameter.id})
        self.authorize(self.trainee, self.parameter)
        self.trainee.unlink()
        self.assertEqual(
            self.authorizations.search([("parameter_id", "=", self.parameter.id)]).person_id.ids,
            (self.tester | self.other_tester | self.head).ids,
        )

    def test_the_assign_dialog_offers_only_authorized_people_and_refuses_another(self):
        task = self.testing_task(self.test)
        wizard = (
            self.env[MODEL_TASK_REASSIGN]
            .with_user(self.head.user_id)
            .with_context(active_ids=task.ids)
            .create({"assignee_id": self.trainee.id})
        )
        self.assertTrue(wizard.authorization_required)
        self.assertEqual(wizard.sudo().authorized_person_ids, self.tester | self.other_tester | self.head)

        with self.assertRaisesRegex(ValidationError, "Do Van Khoa is not authorized to test Lead"):
            wizard.action_confirm()
        self.assertEqual((task.status, task.assignee_id), ("open", self.env["medilab.person"]))
        wizard.assignee_id = self.tester
        wizard.action_confirm()
        self.assertEqual(task.assignee_id, self.tester)

    def test_an_unauthorized_person_cannot_be_assigned_through_rpc_or_the_phone(self):
        task = self.testing_task(self.test)

        with self.assertRaises(ValidationError):
            self.as_person(task, self.head).write({"assignee_id": self.trainee.id, "status": "assigned"})
        with self.assertRaises(ValidationError):
            self.as_person(task, self.head)._assign_from_phone({"assignee_id": self.trainee.id})
        self.assertFalse(task.assignee_id)

    def test_a_task_opening_no_sample_test_goes_to_anyone(self):
        task = self.env[MODEL_TASK].create(
            {
                "type_id": self.env.ref("sol_laboratory.task_type_general").id,
                "name": "Clean the fume hood",
                "assignee_id": self.trainee.id,
                "deadline": MONDAY,
            }
        )
        self.assertEqual(task.assignee_id, self.trainee)

    def test_an_unauthorized_person_neither_sees_nor_claims_the_testing_task(self):
        task = self.testing_task(self.test)
        tasks = self.env[MODEL_TASK]

        self.assertNotIn(task, self.as_person(tasks, self.trainee).search([("in_my_queue", "=", True)]))
        self.assertFalse(self.as_person(task, self.trainee).in_my_queue)
        with self.assertRaisesRegex(ValidationError, "not authorized"):
            self.as_person(task, self.trainee).action_claim()
        self.assertEqual(task.status, "open")
        self.assertIn(task, self.as_person(tasks, self.tester).search([("in_my_queue", "=", True)]))
        self.as_person(task, self.tester).action_claim()
        self.assertEqual(task.assignee_id, self.tester)

    def test_an_unauthorized_person_cannot_be_booked(self):
        task = self.testing_task(self.test, self.tester)
        bookings = self.as_person(self.env[MODEL_MACHINE_BOOKING], self.head)

        with self.assertRaises(ValidationError):
            bookings.create(
                {
                    "machine_id": self.fast.id,
                    "sample_test_id": self.test.id,
                    "task_id": task.id,
                    "person_id": self.trainee.id,
                }
            )
        booking = self.schedule(self.test, self.tester)
        with self.assertRaises(ValidationError):
            self.as_person(booking, self.head).write({"person_id": self.trainee.id})
        self.assertEqual(booking.person_id, self.tester)

    def test_an_assignment_made_before_revoking_stays_but_is_no_longer_booked(self):
        task = self.testing_task(self.test, self.tester)
        self.authorization(self.tester).unlink()

        task.write({"note": "Use the spare column"})
        self.assertEqual(task.assignee_id, self.tester)
        self.assertFalse(self.test.recommended_machine_id)
        with self.assertRaisesRegex(ValidationError, "Le Van Cuong is not authorized to test Lead"):
            self.schedule(self.test, self.tester)
        self.assertFalse(self.test.booking_ids)
