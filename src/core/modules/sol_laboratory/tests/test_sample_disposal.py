from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE, MODEL_SCHEDULED_JOB, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import SAMPLE_RETENTION_CODE


@tagged("post_install", "-at_install")
class TestSampleDisposal(RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.staff = cls.env.ref("sol_laboratory.person_administrator")
        cls.today = cls.env[MODEL_SAMPLE]._company_today()

    def retention_tasks(self, samples):
        return self.env[MODEL_TASK].search(
            [
                ("type_id.code", "=", SAMPLE_RETENTION_CODE),
                ("document_model", "=", MODEL_SAMPLE),
                ("document_id", "in", samples.ids),
            ]
        )

    def test_disposal_without_a_method_is_refused(self):
        self.sample.status = "reported"

        with self.assertRaises(UserError) as refusal:
            self.sample.action_dispose()

        self.assertIn("disposal method", str(refusal.exception).lower())

    def test_the_sample_type_method_is_used_when_the_sample_has_none(self):
        self.sample_type.disposal_method = "Autoclave and landfill"
        self.sample.status = "reported"

        self.sample.with_user(self.staff.user_id).action_dispose()

        self.assertEqual(self.sample.disposal_note, "Autoclave and landfill")

    def test_a_disposed_sample_cannot_be_disposed_again_or_changed_back(self):
        sample = self.sample.with_user(self.staff.user_id)
        self.sample.status = "reported"

        sample.action_dispose("Autoclave and landfill")

        self.assertEqual(sample.status, "disposed")
        self.assertEqual(sample.disposal_note, "Autoclave and landfill")
        self.assertEqual(sample.disposed_by_id, self.staff)
        with self.assertRaises(UserError):
            sample.action_dispose("Autoclave and landfill")
        with self.assertRaises(UserError):
            sample.write({"status": "retained"})

    def test_a_sample_still_retained_or_being_tested_cannot_be_disposed(self):
        self.sample.write({"status": "retained", "retained_until": self.today + timedelta(days=3)})
        with self.assertRaises(UserError):
            self.sample.action_dispose("Poured away")

        self.sample.write({"status": "testing", "retained_until": False})
        with self.assertRaises(UserError):
            self.sample.action_dispose("Poured away")

    def test_retention_reminder_lists_a_sample_due_soon_once(self):
        self.sample.write({"status": "retained", "retained_until": self.today + timedelta(days=3)})
        disposed = self.create_request().sample_ids
        disposed.write({"status": "disposed", "retained_until": self.today + timedelta(days=1)})

        self.env[MODEL_SCHEDULED_JOB]._run_key("sample.retention.reminders")
        self.env[MODEL_SCHEDULED_JOB]._run_key("sample.retention.reminders")
        tasks = self.retention_tasks(self.sample | disposed)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks.document_id, self.sample.id)
        self.assertEqual(tasks.department_id, self.department)
        self.assertEqual(tasks.status, "open")

    def test_disposing_closes_the_retention_reminder(self):
        self.sample.write({"status": "retained", "retained_until": self.today - timedelta(days=1)})
        self.env[MODEL_SCHEDULED_JOB]._run_key("sample.retention.reminders")

        self.sample.with_user(self.staff.user_id).action_dispose("Poured away")

        self.assertEqual(self.retention_tasks(self.sample).status, "done")
