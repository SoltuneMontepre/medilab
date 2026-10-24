from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.laboratory_uploads import VERIFY_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_ITEM, MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestLaboratoryUploadVerificationPass(TransactionCase):
    """A pass of the verification cron reads one file, so several large files never take a pass past the worker's time
    limit."""

    def test_a_pass_of_the_cron_verifies_one_upload_and_leaves_the_others_for_the_next(self):
        jobs = self.env[MODEL_SCHEDULED_JOB]
        job = jobs._by_key(VERIFY_JOB)
        for number in range(3):
            jobs.queue(VERIFY_JOB, f"content:test-{number}")
        handled = []

        def handle(job, item):
            handled.append(item.item_key)

        with patch.object(type(jobs), "_handle_laboratory_contents_verify", handle), self.registry_test_mode():
            job.cron_id.method_direct_trigger()
        self.env.invalidate_all()

        items = self.env[MODEL_JOB_ITEM].search([("job_id", "=", job.id), ("item_key", "=like", "content:test-%")])
        self.assertEqual(handled, ["content:test-0"])
        self.assertEqual(sorted(items.mapped("status")), ["done", "pending", "pending"])
