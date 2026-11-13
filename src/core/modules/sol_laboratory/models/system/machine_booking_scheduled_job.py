from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.fields import Domain
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.jobs import MACHINE_BOOKINGS_OVERRUN_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_MAIL_MESSAGE, MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.constants.notifications import EVENT_MACHINE_BOOKING_OVERRUN

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_scheduled_job as ScheduledJobBase
else:
    ScheduledJobBase = object


# Tác Vụ Định Kỳ
class ScheduledJob(models.Model, ScheduledJobBase):
    _inherit = MODEL_SCHEDULED_JOB

    def _overrun_bookings(self):
        """The machine bookings whose end passed while they still hold their machine: their result is not entered and
        their measurement is not marked finished."""
        return (
            self.env[MODEL_MACHINE_BOOKING]
            .sudo()
            .search(
                Domain("status", "in", ("scheduled", "in_progress"))
                & Domain("machine_id", "!=", False)
                & Domain("ends_at", "<", fields.Datetime.now())
            )
        )

    def _queue_machine_bookings_overrun(self):
        # The item key holds the end, so a booking is notified once for each end it overruns.
        for booking in self._overrun_bookings():
            self.queue(MACHINE_BOOKINGS_OVERRUN_JOB, f"machine_booking:{booking.id}:{booking.ends_at}", booking)

    def _handle_machine_bookings_overrun(self, item):
        booking = item._document()
        if not booking or not booking.exists() or booking not in self._overrun_bookings():
            return
        # ponytail: the at-risk flag of the next bookings' sample tests is this notification until the sample test has
        # its own at-risk flag; nothing moves by itself.
        later = booking.search(
            Domain("machine_id", "=", booking.machine_id.id)
            & Domain("status", "=", "scheduled")
            & Domain("starts_at", ">=", booking.ends_at)
            & Domain("id", "!=", booking.id),
            order="starts_at",
            limit=1,
        )
        following = later and booking.search(
            Domain("machine_id", "=", booking.machine_id.id)
            & Domain("status", "=", "scheduled")
            & Domain("starts_at", "=", later.starts_at)
        )
        zone = self.env.company.tz or "UTC"
        body = self.env._(
            "%(booking)s on %(machine)s ended at %(end)s without its result or a finished measurement, so it still "
            "holds the machine.",
            booking=booking.display_name,
            machine=booking.machine_id.display_name,
            end=format_datetime(self.env, booking.ends_at, tz=zone),
        )
        if following:
            body += " " + self.env._(
                "At risk: %s.", ", ".join(next_booking.display_name or "" for next_booking in following)
            )
        bookings = booking | following
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_MACHINE_BOOKING_OVERRUN,
            booking,
            f"machine_booking:{booking.id}:{booking.ends_at}:overrun",
            body,
            subject=booking.display_name,
            partners=bookings.person_id.user_id.partner_id | bookings.department_id.manager_id.user_id.partner_id,
        )
