from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_ROLE_GRANT, MODEL_SCHEDULED_JOB

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_role_grants_expire(self):
        # The item key holds the last day, so a role extended after it was queued is queued again for its new day.
        for grant in self.env[MODEL_ROLE_GRANT]._lapsed():
            self.queue(self.key, f"role_grant:{grant.id}:{grant.date_end}", document=grant)

    def _handle_role_grants_expire(self, item):
        grant = item._document()
        if grant and grant.exists() and grant in grant._lapsed():
            grant.unlink()
