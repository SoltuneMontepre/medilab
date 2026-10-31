from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SAMPLE,
    MODEL_SCHEDULED_JOB,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.constants.tasks import RETENTION_DUE_TRIGGER, SAMPLE_RETENTION_CODE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

SAMPLE_RETENTION_JOB = "sample.retention.reminders"


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_sample_retention_reminders(self):
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("sample_retention_reminder_days")
        horizon = self.env[MODEL_SAMPLE]._company_today() + timedelta(days=days)
        samples = self.env[MODEL_SAMPLE].sudo().search([("status", "=", "retained"), ("retained_until", "<=", horizon)])
        # The item key is the sample, so a sample is queued once however often the job runs.
        for sample in samples:
            self.queue(SAMPLE_RETENTION_JOB, f"sample:{sample.id}", document=sample)

    def _handle_sample_retention_reminders(self, item):
        sample = item._document()
        if not sample or not sample.exists() or sample.status != "retained":
            return
        tasks = self.env[MODEL_TASK].sudo()
        if tasks.search_count(
            [
                ("type_id.code", "=", SAMPLE_RETENTION_CODE),
                ("document_model", "=", MODEL_SAMPLE),
                ("document_id", "=", sample.id),
            ]
        ):
            return
        department = sample._retention_department()
        if department:
            tasks._create_for_event(RETENTION_DUE_TRIGGER, document=sample, department=department)
