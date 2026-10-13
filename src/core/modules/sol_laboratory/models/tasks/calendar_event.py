from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_TASK

SKIP_SYNC = "medilab_skip_calendar_sync"


# Lịch
class CalendarEvent(models.Model):
    _inherit = "calendar.event"

    # The planned task this event keeps in step with. Machine bookings are not linked here.
    medilab_task_id = fields.Many2one(MODEL_TASK, ondelete="cascade", index=True)

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get(SKIP_SYNC) and {"start", "stop"} & set(vals):
            self._copy_times_to_tasks()
        return result

    def _copy_times_to_tasks(self):
        for event in self.filtered("medilab_task_id"):
            event.medilab_task_id.with_context(**{SKIP_SYNC: True}).write(
                {"planned_start": event.start, "planned_end": event.stop}
            )

    def unlink(self):
        tasks = self.medilab_task_id.with_context(**{SKIP_SYNC: True})
        result = super().unlink()
        tasks.write({"planned_start": False, "planned_end": False})
        return result
