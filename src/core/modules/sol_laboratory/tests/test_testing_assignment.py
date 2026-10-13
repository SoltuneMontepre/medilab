from freezegun import freeze_time

from odoo.tests import Form, tagged

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_PARAMETER_METHOD_MACHINE,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestTestingAssignment(SchedulingCase):
    def assign_sample(self, task, assignee):
        action = task.with_user(self.head.user_id).action_assign_sample()
        wizard = Form(self.env[MODEL_TASK_REASSIGN].with_user(self.head.user_id).with_context(**action["context"]))
        wizard.assignee_id = assignee
        wizard.save().action_confirm()

    def test_assigning_a_sample_assigns_all_its_testing_tasks_in_the_department(self):
        copper = self.create_parameter("Copper (Cu)", self.group)
        self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": copper.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "department_id": self.department.id,
                "is_default": True,
            }
        )
        second = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": copper.id})
        lead_task, copper_task = self.testing_task(self.test), self.testing_task(second)
        self.assign_sample(lead_task, self.tester)
        self.assertEqual((lead_task | copper_task).assignee_id, self.tester)
        self.assertEqual(set((lead_task | copper_task).mapped("status")), {"assigned"})

    def test_an_assigned_testing_task_leaves_the_queue_for_the_assignees_todo_list(self):
        task = self.testing_task(self.test)
        tasks = self.env[MODEL_TASK].with_user(self.tester.user_id)
        self.assertIn(task, tasks.search([("in_my_queue", "=", True)]))
        self.assign_sample(task, self.tester)
        self.assertNotIn(task, tasks.search([("in_my_queue", "=", True)]))
        self.assertIn(task, tasks.search([("is_mine", "=", True)]))

    def test_receiving_a_sample_queues_its_testing_task_due_when_the_test_is_due(self):
        staff = self.env.ref("sol_laboratory.person_administrator").user_id
        self.sample.with_user(staff).action_receive("2 bottles of 1 L", "good")
        task = self.env[MODEL_TASK].search(
            [("document_model", "=", MODEL_SAMPLE_TEST), ("document_id", "=", self.test.id)]
        )
        self.assertEqual((task.department_id, task.status), (self.department, "open"))
        self.assertEqual(task.deadline, self.test.due_date)

    def test_a_reassigned_testing_task_moves_its_booking_to_the_new_assignee(self):
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        task.write({"assignee_id": self.other_tester.id, "reassign_reason": "On leave"})
        self.assertEqual(booking.person_id, self.other_tester)
        self.assertEqual(booking.calendar_event_id.partner_ids, self.other_tester.user_id.partner_id)

    def test_a_head_sees_the_bookings_of_their_department_only(self):
        coliforms = self.create_parameter("Coliforms", self.group)
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": coliforms.id,
                "method_id": self.method.id,
                "unit_id": self.unit.id,
                "department_id": self.microbiology.id,
                "is_default": True,
            }
        )
        incubator = self.env[MODEL_MACHINE].create({"code": "INC-1", "name": "Incubator 1"})
        self.env[MODEL_PARAMETER_METHOD_MACHINE].create(
            {"parameter_method_id": way.id, "machine_id": incubator.id, "run_minutes": 60}
        )
        self.grant(self.microbiologist, "sample_test.read.all")
        self.microbiologist.tz = "UTC"
        other_test = self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": coliforms.id})
        self.testing_task(other_test, self.microbiologist, self.microbiology)
        self.testing_task(self.test, self.tester)
        own = self.schedule(self.test, self.tester)
        other = self.schedule(other_test, self.microbiologist)
        seen = self.env[MODEL_MACHINE_BOOKING].with_user(self.head.user_id).search([])
        self.assertIn(own, seen)
        self.assertNotIn(other, seen)
        self.assertEqual(self.env[MODEL_MACHINE_BOOKING].with_user(self.tester.user_id).search([]), own)

    def test_sending_a_testing_task_back_to_the_queue_cancels_its_booking(self):
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        task.write({"assignee_id": False, "status": "open", "reassign_reason": "Back to the queue"})
        self.assertEqual(booking.status, "cancelled")
        self.assertFalse(booking.calendar_event_id)
