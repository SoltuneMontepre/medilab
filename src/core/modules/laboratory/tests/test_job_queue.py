from odoo.tests import tagged

from .jobs_case import JobsCase
from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT, MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestJobQueue(JobsCase):
    def test_the_same_item_key_is_queued_once(self):
        first = self.queue("delivery:1", payload={"channel": "email"})
        second = self.queue("delivery:1", payload={"channel": "push"})

        self.assertEqual(first, second)
        self.assertEqual(len(self.items()), 1)
        self.assertEqual(first.payload, {"channel": "email"})

    def test_an_item_keeps_its_document_and_payload(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Chemistry"})

        item = self.queue("department:1", payload={"message": "hello"}, document=department)

        self.assertEqual((item.document_model, item.document_id), (MODEL_DEPARTMENT, department.id))
        self.assertEqual(item._document(), department)
        self.assertEqual((item.status, item.attempts), ("pending", 0))

    def test_a_done_item_is_not_queued_again_under_the_same_key(self):
        handled = self.record_handler()
        item = self.queue("delivery:1")
        self.run_pass()

        again = self.queue("delivery:1")

        self.assertEqual(again, item)
        self.assertEqual(again.status, "done")
        self.assertEqual(handled, ["delivery:1"])

    def test_an_unknown_key_is_refused(self):
        with self.assertRaises(ValueError):
            self.env[MODEL_SCHEDULED_JOB].queue("no.such.job", "x")

    def test_a_job_without_a_cron_gets_one(self):
        job = self.env[MODEL_SCHEDULED_JOB].create({"key": "test.other", "name": "Other"})

        self.assertEqual(job.cron_id.code, 'model._run_key("test.other")')
        self.assertEqual(job.cron_id.model_id.model, MODEL_SCHEDULED_JOB)
