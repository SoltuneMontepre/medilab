from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_LOCK, MODEL_SCHEDULED_JOB

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_laboratory_file_locks_expire(self):
        # The item key is the lock and when it expires, so a lock renewed after it was queued is queued again once it
        # expires.
        for lock in self.env[MODEL_LABORATORY_FILE_LOCK]._stale():
            stamp = fields.Datetime.to_string(lock.expires_at)
            self.queue(self.key, f"lock:{lock.id}:{stamp}", document=lock)

    def _handle_laboratory_file_locks_expire(self, item):
        lock = item._document()
        if lock and lock.exists() and not lock._in_force():
            lock._expire()
