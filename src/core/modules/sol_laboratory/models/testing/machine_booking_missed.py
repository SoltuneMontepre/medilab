from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING
from odoo.addons.sol_laboratory.models.testing.machine_booking import HORIZON_DAYS

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingMissedBase
else:
    MachineBookingMissedBase = object


# Lịch Đặt Máy: a tester who missed the start of a booking books the next free slot themselves.
class MachineBookingMissed(models.Model, MachineBookingMissedBase):
    _inherit = MODEL_MACHINE_BOOKING

    if not TYPE_CHECKING:
        # True when the booking is scheduled and its start has passed without the tester starting it.
        is_missed = fields.Boolean(compute="_compute_is_missed", search="_search_is_missed")

    @api.model
    def _missed_domain(self):
        return Domain("status", "=", "scheduled") & Domain("starts_at", "<", fields.Datetime.now())

    def _missed(self):
        now = fields.Datetime.now()
        return self.filtered(
            lambda booking: booking.status == "scheduled" and bool(booking.starts_at) and booking.starts_at < now
        )

    @api.depends("status", "starts_at")
    def _compute_is_missed(self):
        missed = self._missed()
        missed.is_missed = True
        (self - missed).is_missed = False

    def _search_is_missed(self, operator, value):
        if operator not in ("=", "!="):
            raise NotImplementedError(f"is_missed does not support {operator}")
        return self._missed_domain() if (operator == "=") == bool(value) else ~self._missed_domain()

    def action_reschedule(self):
        """Move missed bookings to the earliest slot that is free now for their tester, machine and rooms; the person who
        runs a booking does it, or whoever may edit it, who pins it as for any move."""
        self._check_adjustable()
        horizon = fields.Datetime.now() + timedelta(days=HORIZON_DAYS)
        if self - self._missed():
            raise UserError(self.env._("Only a scheduled booking whose start has passed can be rescheduled."))
        for booking in self:
            way = booking.sample_test_id.parameter_method_id
            slot = self._free_slot(
                booking.machine_id,
                booking.ends_at - booking.starts_at,
                booking.person_id,
                horizon,
                ignore=booking,
                rooms=self._room_steps(way),
                way=way,
                sample=booking.sample_test_id.sample_id,
            )
            if not slot:
                raise UserError(
                    self.env._(
                        "No slot is free for %(booking)s in the next %(days)s days; ask the head of the department.",
                        booking=booking.display_name,
                        days=HORIZON_DAYS,
                    )
                )
            booking._move(slot)
