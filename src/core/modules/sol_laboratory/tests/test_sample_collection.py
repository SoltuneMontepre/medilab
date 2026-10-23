from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PERSON,
    MODEL_SAMPLE,
    MODEL_SCHEDULED_JOB,
    MODEL_TASK,
    MODEL_TASK_TYPE,
)
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_COLLECTION_CODE


@tagged("post_install", "-at_install")
class TestSampleCollection(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env.ref("sol_laboratory.person_administrator")
        cls.delivery = cls.env[MODEL_PERSON].create(
            {"name": "Pham Van Giao", "login": "giao.pham", "work_email": "giao.pham@example.com"}
        )
        cls.delivery.user_id.notification_type = "inbox"

    def collection_task(self, start):
        return self.env[MODEL_TASK].create(
            {
                "type_id": self.env[MODEL_TASK_TYPE].search([("code", "=", SAMPLE_COLLECTION_CODE)], limit=1).id,
                "name": f"Collect {self.sample.code}",
                "assignee_id": self.delivery.id,
                "deadline": start + timedelta(hours=1),
                "planned_start": start,
                "planned_end": start + timedelta(hours=1),
                "document_model": MODEL_SAMPLE,
                "document_id": self.sample.id,
            }
        )

    def test_collection_task_is_on_the_schedule_and_the_todo_list(self):
        task = self.collection_task(fields.Datetime.now() + timedelta(days=1))

        todo = self.env[MODEL_TASK].with_user(self.delivery.user_id).search([("is_mine", "=", True)])
        self.assertIn(task, todo)
        event = self.env["calendar.event"].search([("medilab_task_id", "=", task.id)])
        self.assertEqual(event.start, task.planned_start)
        self.assertIn(self.delivery.user_id.partner_id, event.partner_ids)

    def test_a_reminder_arrives_before_the_collection_starts(self):
        task = self.collection_task(fields.Datetime.now() + timedelta(minutes=10))

        self.env[MODEL_SCHEDULED_JOB]._run_key("notifications.remind")

        reminder = self.env["mail.message"].search([("model", "=", MODEL_TASK), ("res_id", "=", task.id)])
        self.assertEqual(reminder.subtype_id, self.env.ref("sol_laboratory.event_task_reminder"))
        self.assertIn(self.delivery.user_id.partner_id, reminder.notification_ids.res_partner_id)

    def test_a_collection_task_is_marked_done_by_hand(self):
        task = self.collection_task(fields.Datetime.now() + timedelta(days=1))

        task.with_user(self.delivery.user_id).action_done()

        self.assertEqual(task.status, "done")

    def test_recollection_task_shows_the_sample_it_is_for(self):
        sample = self.sample.with_user(self.staff.user_id)
        sample.action_receive("50 mL", "insufficient")

        sample.with_user(self.head_of(self.department).user_id).action_request_recollection()
        task = self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_COLLECTION_CODE),
                ("document_model", "=", MODEL_SAMPLE),
                ("document_id", "=", sample.id),
            ]
        )

        self.assertEqual((task.document_model, task.document_id), (MODEL_SAMPLE, sample.id))
        self.assertEqual(task.action_open_document()["res_id"], sample.id)
        self.assertTrue(self.env["calendar.event"].search([("medilab_task_id", "=", task.id)]))
