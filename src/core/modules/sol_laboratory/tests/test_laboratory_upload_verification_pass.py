from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.laboratory_uploads import VERIFY_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_CRON, MODEL_JOB_ITEM, MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestLaboratoryUploadVerificationPass(TransactionCase):
    """A pass of the verification cron reads one file, so several large files never take a pass past the worker's time
    limit, and wakes the cron worker for the next file at once."""

    def run_pass(self, count):
        """Queue the items, run one pass of the verification cron, and return the items it handled and the crons it
        triggered."""
        jobs = self.env[MODEL_SCHEDULED_JOB]
        job = jobs._by_key(VERIFY_JOB)
        for number in range(count):
            jobs.queue(VERIFY_JOB, f"content:test-{number}")
        handled = []
        triggered = []

        def handle(job, item):
            handled.append(item.item_key)

        def trigger(cron, *args, **kwargs):
            triggered.append(cron.id)

        with (
            patch.object(type(jobs), "_handle_laboratory_contents_verify", handle),
            patch.object(type(self.env[MODEL_IR_CRON]), "_trigger", trigger),
            self.registry_test_mode(),
        ):
            job.cron_id.method_direct_trigger()
        self.env.invalidate_all()
        return job, handled, triggered

    def test_a_pass_of_the_cron_verifies_one_upload_and_leaves_the_others_for_the_next(self):
        job, handled, triggered = self.run_pass(3)

        items = self.env[MODEL_JOB_ITEM].search([("job_id", "=", job.id), ("item_key", "=like", "content:test-%")])
        self.assertEqual(handled, ["content:test-0"])
        self.assertEqual(sorted(items.mapped("status")), ["done", "pending", "pending"])
        self.assertEqual(triggered, [job.cron_id.id])

    def test_a_pass_that_verifies_the_last_upload_triggers_no_other_pass(self):
        _job, handled, triggered = self.run_pass(1)

        self.assertEqual(handled, ["content:test-0"])
        self.assertEqual(triggered, [])
