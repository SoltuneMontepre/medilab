from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import MODEL_CALENDAR_EVENT, MODEL_LOCATION_UNAVAILABILITY

if TYPE_CHECKING:
    from medilab_model_types import Model_calendar_event as CalendarEventUnavailabilityBase
else:
    CalendarEventUnavailabilityBase = object


# Lịch: a location is not booked while it cannot be used.
class CalendarEventUnavailability(models.Model, CalendarEventUnavailabilityBase):
    _inherit = MODEL_CALENDAR_EVENT

    @api.constrains("location_id", "start", "stop", "active")
    def _check_location_available(self):
        closures = self.env[MODEL_LOCATION_UNAVAILABILITY].sudo()
        # A measurement already started keeps the rooms of its steps.
        for event in self.filtered(
            lambda event: bool(event.location_id and event.active) and event.machine_booking_id.status != "in_progress"
        ):
            closure = closures.search(
                [
                    ("location_id", "=", event.location_id.id),
                    ("starts_at", "<", event.stop),
                    ("ends_at", ">", event.start),
                ],
                limit=1,
            )
            if closure:
                raise ValidationError(
                    self.env._(
                        "%(location)s cannot be used from %(start)s to %(end)s: %(reason)s",
                        location=closure.location_id.display_name,
                        start=format_datetime(self.env, closure.starts_at),
                        end=format_datetime(self.env, closure.ends_at),
                        reason=closure.reason,
                    )
                )
