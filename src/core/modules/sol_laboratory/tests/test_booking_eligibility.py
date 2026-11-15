from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.tests import tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RECEIVED_TRIGGER


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestBookingEligibility(SchedulingCase):
    def assigned_unreceived(self):
        """A lead test whose testing task the tester holds while its sample has not reached the department."""
        test = self.new_test()
        test.sample_id.status = "received"
        task = self.env[MODEL_TASK]._create_for_event(
            SAMPLE_RECEIVED_TRIGGER, document=test, department=self.department
        )
        task.write({"assignee_id": self.tester.id, "status": "assigned"})
        return test, task

    def test_a_sample_test_is_booked_once_its_department_received_the_sample(self):
        test, _task = self.assigned_unreceived()

        self.assertFalse(test.recommended_machine_id)
        with self.assertRaisesRegex(UserError, "waits until its department receives its sample"):
            self.schedule(test, self.tester)
        self.receive(test.sample_id, self.microbiology)
        with self.assertRaisesRegex(UserError, "waits until its department receives its sample"):
            self.schedule(test, self.tester)
        self.assertFalse(test.booking_ids)

        self.receive(test.sample_id, self.department)
        self.assertEqual(self.schedule(test, self.tester).status, "scheduled")

    def test_a_sample_on_hold_is_not_booked(self):
        task = self.testing_task(self.test, self.tester)
        self.sample.status = "on_hold"

        self.assertFalse(self.test.recommended_machine_id)
        with self.assertRaisesRegex(UserError, "its sample is on hold"):
            self.schedule(self.test, self.tester)
        with self.assertRaisesRegex(UserError, "its sample is on hold"):
            self.as_person(self.env[MODEL_MACHINE_BOOKING], self.head).create(
                {"machine_id": self.fast.id, "sample_test_id": self.test.id, "task_id": task.id}
            )
        self.assertFalse(self.test.booking_ids)

    def test_a_cancelled_sample_test_is_not_booked(self):
        self.testing_task(self.test, self.tester)
        self.test.status = "cancelled"

        with self.assertRaisesRegex(UserError, "is cancelled"):
            self.schedule(self.test, self.tester)
        self.assertFalse(self.test.booking_ids)

    def test_a_booking_cannot_be_created_through_rpc_for_an_unreceived_sample(self):
        test, task = self.assigned_unreceived()

        with self.assertRaisesRegex(UserError, "waits until its department receives its sample"):
            self.as_person(self.env[MODEL_MACHINE_BOOKING], self.head).create(
                {"machine_id": self.fast.id, "sample_test_id": test.id, "task_id": task.id, "person_id": self.tester.id}
            )
        self.assertFalse(test.booking_ids)
