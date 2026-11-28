from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .scheduling_case import MONDAY, SchedulingCase, calibrated
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE,
    MODEL_MACHINE_BOOKING,
    MODEL_MACHINE_METHOD,
    MODEL_PARAMETER_METHOD,
    MODEL_PERSON,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TASK_REASSIGN,
    MODEL_TESTING_METHOD,
)


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestTestingAssignment(SchedulingCase):
    def reassign(self, tasks, **vals):
        wizard = self.as_person(self.env[MODEL_TASK_REASSIGN], self.head).with_context(active_ids=tasks.ids)
        return wizard.create(vals)

    def coliforms_test(self):
        """A coliforms test of the sample, which Microbiology tests."""
        coliforms = self.create_parameter("Coliforms", self.group)
        method = self.env[MODEL_TESTING_METHOD].create(
            {"code": "TCVN 6187-2:2020", "name": "Coliforms by MPN", "field_id": self.testing_field.id}
        )
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {"parameter_id": coliforms.id, "method_id": method.id, "department_id": self.microbiology.id}
        )
        self.offer(coliforms, self.sample_type, way)
        return self.env[MODEL_SAMPLE_TEST].create({"sample_id": self.sample.id, "parameter_id": coliforms.id})

    def assign_sample(self, task, assignee):
        action = task.with_user(self.head.user_id).action_assign_sample()
        wizard = Form(self.env[MODEL_TASK_REASSIGN].with_user(self.head.user_id).with_context(**action["context"]))
        wizard.assignee_id = assignee
        wizard.save().action_confirm()

    def test_assigning_a_sample_assigns_all_its_testing_tasks_in_the_department(self):
        copper = self.create_parameter("Copper (Cu)", self.group)
        way = self.env[MODEL_PARAMETER_METHOD].create(
            {
                "parameter_id": copper.id,
                "method_id": self.method.id,
                "department_id": self.department.id,
            }
        )
        self.offer(copper, self.sample_type, way)
        self.authorize(self.tester, copper)
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

    def test_a_reassigned_testing_task_returns_its_booking_to_the_plan_for_the_new_assignee(self):
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        task.write({"assignee_id": self.other_tester.id, "reassign_reason": "On leave"})
        self.assertEqual((booking.status, booking.person_id), ("proposed", self.other_tester))
        self.assertFalse(booking.calendar_event_id)
        booking.with_user(self.head.user_id).action_approve()
        self.assertEqual(booking.calendar_event_id.partner_ids, self.other_tester.user_id.partner_id)

    def test_a_head_sees_the_bookings_of_their_department_only(self):
        other_test = self.coliforms_test()
        incubator = self.env[MODEL_MACHINE].create(calibrated({"code": "INC-1", "name": "Incubator 1"}))
        self.env[MODEL_MACHINE_METHOD].create(
            {
                "method_id": other_test.parameter_id.method_ids.method_id.id,
                "machine_id": incubator.id,
                "duration_minutes": 60,
            }
        )
        self.grant(self.microbiologist, "sample_test.read.all")
        self.microbiologist.tz = "UTC"
        self.testing_task(other_test, self.microbiologist, self.microbiology)
        self.testing_task(self.test, self.tester)
        own = self.schedule(self.test, self.tester)
        other = self.schedule(other_test, self.microbiologist)
        seen = self.env[MODEL_MACHINE_BOOKING].with_user(self.head.user_id).search([])
        self.assertIn(own, seen)
        self.assertNotIn(other, seen)
        self.assertEqual(self.env[MODEL_MACHINE_BOOKING].with_user(self.tester.user_id).search([]), own)

    def test_sending_a_testing_task_back_to_the_queue_returns_its_booking_to_the_plan_without_a_tester(self):
        task = self.testing_task(self.test, self.tester)
        booking = self.schedule(self.test, self.tester)
        task.write({"assignee_id": False, "status": "open", "reassign_reason": "Back to the queue"})
        self.assertEqual((booking.status, booking.person_id), ("proposed", self.env[MODEL_PERSON]))
        self.assertFalse(booking.calendar_event_id)

    def test_the_test_is_assigned_with_its_testing_task_and_waits_again_back_in_the_queue(self):
        task = self.testing_task(self.test)
        self.assertEqual(self.test.status, "waiting")

        self.as_person(task, self.tester).action_claim()
        self.assertEqual(self.test.status, "assigned")

        wizard = self.as_person(self.env[MODEL_TASK_REASSIGN], self.head).with_context(active_ids=task.ids)
        wizard.create(
            {"department_id": self.department.id, "assignee_id": False, "reason": "The tester is on leave"}
        ).action_confirm()
        self.assertEqual((task.status, self.test.status), ("open", "waiting"))

    def test_the_assign_wizard_offers_only_the_department_of_a_testing_tasks_way(self):
        task = self.testing_task(self.test)

        wizard = Form(self.env[MODEL_TASK_REASSIGN].with_user(self.head.user_id).with_context(active_ids=task.ids))
        self.assertEqual(wizard.department_id, self.department)
        self.assertTrue(wizard.department_fixed)
        with self.assertRaises(AssertionError):
            wizard.department_id = self.microbiology

    def test_a_testing_task_moved_to_another_department_through_the_wizard_is_refused(self):
        task = self.testing_task(self.test)

        with self.assertRaisesRegex(ValidationError, "stay in"):
            self.reassign(task, department_id=self.microbiology.id, reason="Needs a culture").action_confirm()
        self.assertEqual((task.department_id, task.status), (self.department, "open"))

    def test_a_testing_task_written_into_another_department_is_refused(self):
        task = self.testing_task(self.test)

        with self.assertRaisesRegex(ValidationError, "cannot move to another department"):
            task.write({"department_id": self.microbiology.id, "reassign_reason": "Needs a culture"})
        self.assertEqual(task.department_id, self.department)

    def test_testing_tasks_of_different_departments_are_assigned_separately(self):
        tasks = self.testing_task(self.test) | self.testing_task(self.coliforms_test(), department=self.microbiology)

        wizard = self.env[MODEL_TASK_REASSIGN].with_context(active_ids=tasks.ids).create({})
        self.assertTrue(wizard.department_fixed)
        self.assertFalse(wizard.department_id)
        with self.assertRaisesRegex(ValidationError, "separately"):
            wizard.action_confirm()
        self.assertEqual(tasks.department_id, self.department | self.microbiology)
