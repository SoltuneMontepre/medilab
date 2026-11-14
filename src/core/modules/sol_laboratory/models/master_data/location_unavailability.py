from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_datetime

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_CALENDAR_EVENT,
    MODEL_LOCATION,
    MODEL_LOCATION_UNAVAILABILITY,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_location_unavailability as LocationUnavailabilityBase
else:
    LocationUnavailabilityBase = object


# Thời Gian Ngưng Sử Dụng Vị Trí
class LocationUnavailability(models.Model, LocationUnavailabilityBase):
    _name = MODEL_LOCATION_UNAVAILABILITY
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Location Unavailability"
    _order = "starts_at desc, id desc"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The bookable location that cannot be used.
        location_id = fields.Many2one(
            MODEL_LOCATION, required=True, ondelete="cascade", domain="[('is_bookable', '=', True)]"
        )
        # Start of the interval.
        starts_at = fields.Datetime(string="Start", required=True)
        # End of the interval.
        ends_at = fields.Datetime(string="End", required=True)
        # Why the location cannot be used, such as cleaning or a broken fume hood.
        reason = fields.Text(required=True)

    _location_start_idx = models.Index("(location_id, starts_at)")
    _period = models.Constraint("CHECK(ends_at > starts_at)", "An unavailable interval ends after it starts.")

    @api.depends("location_id", "starts_at", "ends_at")
    def _compute_display_name(self):
        for closure in self:
            closure.display_name = (
                f"{closure.location_id.display_name}: {format_datetime(self.env, closure.starts_at)} – "
                f"{format_datetime(self.env, closure.ends_at)}"
            )

    @api.model_create_multi
    def create(self, vals_list):
        closures = super().create(vals_list)
        closures._return_bookings()
        return closures

    def write(self, vals):
        result = super().write(vals)
        if {"location_id", "starts_at", "ends_at"} & set(vals):
            self._return_bookings()
        return result

    def _return_bookings(self):
        """Return the scheduled machine bookings whose step rooms the intervals overlap to the plan, with the bookings
        sharing their machine interval, which use the same rooms."""
        zone = self.env.company.tz or "UTC"
        for closure in self.sudo():
            events = (
                self.env[MODEL_CALENDAR_EVENT]
                .sudo()
                .search(
                    Domain("location_id", "=", closure.location_id.id)
                    & Domain("start", "<", closure.ends_at)
                    & Domain("stop", ">", closure.starts_at)
                    & Domain("machine_booking_id.status", "=", "scheduled")
                )
            )
            bookings = events.machine_booking_id
            for booking in events.machine_booking_id:
                bookings |= booking._sharing()
            bookings.filtered(lambda booking: booking.status == "scheduled")._return_to_plan(
                self.env._(
                    "%(location)s cannot be used from %(start)s to %(end)s: %(reason)s",
                    location=closure.location_id.display_name,
                    start=format_datetime(self.env, closure.starts_at, tz=zone),
                    end=format_datetime(self.env, closure.ends_at, tz=zone),
                    reason=closure.reason,
                )
            )

    def _in_use_domain(self):
        # An unavailable interval is history and never keeps its location in use.
        return Domain.FALSE
