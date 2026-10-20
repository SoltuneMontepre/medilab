from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CALENDAR_EVENT,
    MODEL_MACHINE_BOOKING,
    MODEL_TASK,
)

SKIP_SYNC = "medilab_skip_calendar_sync"


# Lịch
class CalendarEvent(models.Model):
    _name = MODEL_CALENDAR_EVENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_CALENDAR_EVENT]

    # The planned task this event keeps in step with.
    medilab_task_id = fields.Many2one(MODEL_TASK, ondelete="cascade", index=True)
    # The machine booking whose slot the event shows.
    medilab_booking_ids = fields.One2many(MODEL_MACHINE_BOOKING, "calendar_event_id", string="Machine Bookings")

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get(SKIP_SYNC) and {"start", "stop"} & set(vals):
            self._copy_times_to_tasks()
            self._move_bookings()
        return result

    def _copy_times_to_tasks(self):
        for event in self.filtered("medilab_task_id"):
            event.medilab_task_id.with_context(**{SKIP_SYNC: True}).write(
                {"planned_start": event.start, "planned_end": event.stop}
            )

    def _move_bookings(self):
        # The booking moves only to a free slot, then puts the event back on its own times.
        for booking in self.sudo().medilab_booking_ids:
            booking.with_env(self.env)._move(booking.calendar_event_id.start)

    def unlink(self):
        tasks = self.medilab_task_id.with_context(**{SKIP_SYNC: True})
        result = super().unlink()
        tasks.write({"planned_start": False, "planned_end": False})
        return result
