from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DIGITAL_SIGNING_MIXIN,
    MODEL_SCHEDULED_JOB,
    MODEL_SIGNING_CERTIFICATE,
)
from odoo.addons.sol_laboratory.constants.signing import SIGNING_CERTIFICATES_JOB

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _run_batch(self):
        if self.key == SIGNING_CERTIFICATES_JOB and self.env[MODEL_DIGITAL_SIGNING_MIXIN]._digital_signing_enabled():
            # The alerts read the validity already stored, so they are raised while Viettel Sign is down too.
            self.env[MODEL_SIGNING_CERTIFICATE]._alert()
            self.queue(SIGNING_CERTIFICATES_JOB, f"refresh:{fields.Date.today()}")
        return super()._run_batch()

    def _handle_digital_signing_sign(self, item):
        document = item._document()
        if document and document.exists() and document.digital_signing_pending:
            document._digital_sign()

    def _handle_digital_signing_certificates(self, item):
        certificates = self.env[MODEL_SIGNING_CERTIFICATE]
        certificates._refresh()
        certificates._alert()
