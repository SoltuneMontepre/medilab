from odoo.tests import tagged
from odoo.tools import mute_logger

from .audit_case import AuditLookup
from .jobs_case import JOB_LOGGER, JobsCase
from odoo.addons.sol_laboratory.constants.models import MODEL_UNIT_CATEGORY
from odoo.addons.sol_laboratory.models.system.scheduled_job import PermanentJobError


@tagged("post_install", "-at_install")
class TestAuditJobs(AuditLookup, JobsCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env[MODEL_UNIT_CATEGORY].create({"name": "Volume"})

    def rename_category(self):
        def handler(job, item):
            self.category.with_env(job.env).name = item.item_key

        self.handle_with(handler)

    def test_the_entries_of_a_scheduled_run_have_the_job_source_and_link_the_run(self):
        self.rename_category()
        self.queue("Volume per volume")

        self.run_pass()

        run = self.job.run_ids
        edit = self.entries(self.category, "edit")
        self.assertEqual((edit.source, edit.user_id, edit.job_run_id), ("job", self.env["res.users"], run))
        job_entry = self.entries(self.job, "job")
        self.assertEqual((job_entry.source, job_entry.job_run_id), ("job", run))
        self.assertEqual(job_entry.note, "Succeeded: 1 done, 0 failed")

    def test_a_run_by_hand_is_recorded_as_the_person_who_ran_it(self):
        administrator = self.env.ref("base.user_admin")
        self.rename_category()
        self.queue("Volume per volume")

        self.job.with_user(administrator).action_run()
        self.run_pass()

        self.assertEqual(self.entries(self.category, "edit").user_id, administrator)
        self.assertEqual(self.entries(self.job, "job").user_id, administrator)

    @mute_logger(JOB_LOGGER)
    def test_an_item_that_fails_for_good_writes_an_error(self):
        def handler(job, item):
            raise PermanentJobError("The customer has no email address")

        self.handle_with(handler)
        self.queue("notify.customer.7")

        self.run_pass()

        error = self.entries(self.job, "error")
        self.assertEqual(error.note, "notify.customer.7: The customer has no email address")
        self.assertEqual(error.job_run_id, self.job.run_ids)
        self.assertEqual(self.entries(self.job, "job").note, "Failed: 0 done, 1 failed")

    @mute_logger(JOB_LOGGER)
    def test_an_item_out_of_attempts_writes_an_error(self):
        self.job.max_attempts = 1

        def handler(job, item):
            raise ValueError("The Brevo API is down")

        self.handle_with(handler)
        self.queue("notify.customer.8")

        self.run_pass()

        self.assertEqual(self.entries(self.job, "error").note, "notify.customer.8: ValueError: The Brevo API is down")

    def test_a_job_schedule_kept_on_its_cron_is_recorded_on_the_job(self):
        self.job.write({"interval_number": 2, "interval_type": "hours"})

        self.assertEqual(
            self.changes(self.entries(self.job, "edit")),
            {"interval_number": ("1", "2"), "interval_type": ("days", "hours")},
        )
