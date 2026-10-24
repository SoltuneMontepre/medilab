from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT, MODEL_SCHEDULED_JOB


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_laboratory_contents_reconcile(self):
        # One item per finding, keyed by what it is about, so a finding that stays is recorded once and not every day.
        for item_key, payload in self.env[MODEL_LABORATORY_CONTENT]._reconcile_findings():
            self.queue(self.key, item_key, payload=payload)

    def _handle_laboratory_contents_reconcile(self, item):
        self.env[MODEL_LABORATORY_CONTENT]._reconcile(item.payload)
