from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.jobs import TEST_REPORT_PREPARE_JOB
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_SCHEDULED_JOB,
    MODEL_TEST_REPORT,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object

# Minutes the job waits for ONLYOFFICE to come back before it tries a report again.
OUTAGE_RETRY_MINUTES = 5


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_test_report_prepare(self):
        # The item key holds how many PDFs were prepared, so a report is queued again after its PDF was prepared and
        # went out of date, or was rejected, while an item that keeps failing is not queued again.
        for report in self.env[MODEL_TEST_REPORT].sudo().search([("status", "=", "draft")]):
            if report._pdf_needed():
                self.queue(TEST_REPORT_PREPARE_JOB, f"report:{report.id}:{len(report.candidate_ids)}", report)

    def _handle_test_report_prepare(self, item):
        report = item._document()
        if not report or not report.exists() or not report._pdf_needed():
            return None
        try:
            self.env[MODEL_LABORATORY_EDITING_SESSION]._check_editing_available()
        except LaboratoryFileError:
            # An outage is no failed attempt: the report waits until ONLYOFFICE answers again.
            return fields.Datetime.now() + timedelta(minutes=OUTAGE_RETRY_MINUTES)
        report._prepare_pdf(reason=self.env._("The report changed since its PDF was prepared."))
        return None
