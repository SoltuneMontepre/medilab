from datetime import timedelta

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, tagged

from .scheduling_case import MONDAY
from .task_link_case import TaskLinkCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import TESTING_ACTION


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestTaskDocumentLink(TaskLinkCase):
    def test_the_planner_reads_no_sample_test(self):
        with self.assertRaises(AccessError):
            self.as_person(self.test, self.planner).read(["parameter_method_id"])

    def test_a_task_made_by_hand_cannot_link_a_document(self):
        for vals in (
            {"document_model": MODEL_SAMPLE_TEST, "document_id": self.test.id, "action": TESTING_ACTION},
            {"document_model": MODEL_SAMPLE_TEST, "document_id": self.test.id},
            {"document_id": self.test.id},
            {"action": TESTING_ACTION},
        ):
            with self.subTest(**vals), self.assertRaises(UserError):
                self.hand_task(**vals)
        self.assertFalse(self.env[MODEL_TASK].search([("assignee_id", "=", self.planner.id)]))

    def test_a_task_made_by_hand_cannot_claim_the_system_linked_it(self):
        with self.assertRaises(UserError):
            self.hand_task(linked_by_system=True)
        task = self.hand_task()
        with self.assertRaises(UserError):
            self.as_person(task, self.planner).write({"linked_by_system": True})
        self.assertFalse(task.linked_by_system)

    def test_a_task_made_by_hand_cannot_become_a_testing_task(self):
        task = self.hand_task()
        for vals in (
            {"type_id": self.testing_type.id},
            {"document_model": MODEL_SAMPLE_TEST},
            {"document_id": self.test.id},
            {"action": TESTING_ACTION},
        ):
            with self.subTest(**vals), self.assertRaises(UserError):
                self.as_person(task, self.planner).write(vals)
        self.env.invalidate_all()
        self.assertEqual(
            [task.type_id, task.document_model, task.document_id, task.action], [self.general, False, 0, False]
        )
        self.assertFalse(self.as_person(task, self.planner).method_step_ids)

    def test_a_testing_task_cannot_be_pointed_at_another_test(self):
        task = self.testing_task(self.test, self.tester)
        other = self.new_test()
        for vals in ({"document_id": other.id}, {"document_model": "medilab.sample"}, {"type_id": self.general.id}):
            with self.subTest(**vals), self.assertRaises(UserError):
                self.as_person(task, self.planner).write(vals)
        self.env.invalidate_all()
        self.assertEqual([task.document_model, task.document_id], [MODEL_SAMPLE_TEST, self.test.id])

    def test_the_planner_still_creates_and_reassigns_tasks_by_hand(self):
        task = self.hand_task(note="Calibrate before the run.")
        self.as_person(task, self.planner).write(
            {"assignee_id": self.tester.id, "reassign_reason": "Cuong runs the balance today."}
        )

        self.assertEqual([task.assignee_id, task.document_id, task.action], [self.tester, 0, False])

    def test_a_task_made_in_the_form_keeps_the_action_of_its_type(self):
        collection = self.env.ref("sol_laboratory.task_type_sample_collection")
        with Form(self.as_person(self.env[MODEL_TASK], self.planner)) as form:
            form.type_id = collection
            form.name = "Collect water at the An Phu plant"
            form.assignee_id = self.planner
            form.deadline = MONDAY + timedelta(days=1)
        task = form.record

        self.assertEqual([task.action, task.document_id], [collection.action, 0])
        self.assertFalse(task.method_step_ids)

    def test_a_system_testing_task_still_shows_its_steps(self):
        task = self.testing_task(self.test, self.tester)
        runner = self.create_person("Vo Thi Giang", self.department, "giang.vo")
        task.write({"assignee_id": runner.id, "reassign_reason": "Giang has the free slot."})
        self.env.invalidate_all()

        self.assertEqual(self.as_person(task, runner).method_step_ids.mapped("instruction"), ["Weigh the sample."])
