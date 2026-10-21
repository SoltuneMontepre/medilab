from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION, MODEL_SCHEDULED_JOB


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model):
    _inherit = MODEL_SCHEDULED_JOB

    def _queue_laboratory_editing_sessions_expire(self):
        # The item key is the session and its last activity, so a session is queued once for each time it goes idle.
        for session in self.env[MODEL_LABORATORY_EDITING_SESSION]._idle():
            stamp = fields.Datetime.to_string(session.last_activity_at)
            self.queue(self.key, f"session:{session.id}:{stamp}", document=session)

    def _handle_laboratory_editing_sessions_expire(self, item):
        session = item._document()
        if session and session.exists():
            session._expire()
