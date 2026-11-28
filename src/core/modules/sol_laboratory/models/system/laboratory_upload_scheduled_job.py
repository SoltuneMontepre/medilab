from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.laboratory_uploads import UPLOAD_JOB_FAILURES, VERIFY_JOB, VERIFYING
from odoo.addons.sol_laboratory.constants.models import MODEL_JOB_RUN, MODEL_LABORATORY_UPLOAD, MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.models.system.scheduled_job import CRON_PASS_KEY
from odoo.addons.sol_laboratory.services.type_values import value_as

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        # A verification reads a file of up to 5 GiB, so a pass of the cron does one: Odoo calls a job's batches again
        # for at least 10 batches or 2 minutes, which several files would take past the worker's time limit. A batch
        # that claims nothing ends the pass, and triggers the next pass at once: Odoo's own rescheduling does not wake
        # the cron worker, which would then wait up to a minute for each file.
        if self.key == VERIFY_JOB and self._in_cron() and self._handled_in_this_pass():
            remaining = self._due_count(fields.Datetime.now())
            if remaining:
                self.cron_id._trigger()
            self._progress(remaining=remaining)
            return self.env[MODEL_JOB_RUN]
        return super()._run_batch()

    def _handled_in_this_pass(self):
        cron_pass = str(self.env.context.get(CRON_PASS_KEY))
        runs = self.env[MODEL_JOB_RUN].sudo().search([("job_id", "=", self.id), ("cron_pass", "=", cron_pass)])
        return any(run.done_count or run.failed_count for run in runs)

    def _item_failed(self, item):
        # An upload whose verification or storing failed for good ends failed, so the computer stops waiting for it.
        super()._item_failed(item)
        code = UPLOAD_JOB_FAILURES.get(value_as(self.key, str))
        upload = item._document() if code else None
        if upload and upload.exists() and upload.status == VERIFYING:
            upload._fail(code)

    def _handle_laboratory_contents_verify(self, item):
        upload = item._document()
        if upload and upload.exists():
            upload._verify()

    def _handle_laboratory_uploads_store(self, item):
        upload = item._document()
        if upload and upload.exists():
            upload._store()

    def _queue_laboratory_uploads_expire(self):
        for upload in self.env[MODEL_LABORATORY_UPLOAD]._unfinished():
            self.queue(self.key, f"upload:{upload.id}", document=upload)

    def _handle_laboratory_uploads_expire(self, item):
        upload = item._document()
        if upload and upload.exists():
            upload._expire()
