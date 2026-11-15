from collections import defaultdict
from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING
from odoo.addons.sol_laboratory.models.testing.machine_booking import ACTIVE_STATUSES

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingBase
else:
    MachineBookingBase = object


# Lịch Máy: checks occupied places when a machine-and-method capacity changes.
class MachineBookingCapacity(models.Model, MachineBookingBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.model
    def _check_machine_method_capacity(self, link):
        bookings = self.sudo().search(
            [
                ("machine_id", "=", link.machine_id.id),
                ("method_id", "=", link.method_id.id),
                ("status", "in", ACTIVE_STATUSES),
            ]
        )
        loads = defaultdict(set)
        for booking in bookings:
            loads[booking.starts_at, booking.ends_at].add(booking.sample_test_id.sample_id.id)
        for samples in loads.values():
            if len(samples) > link.capacity:
                raise ValidationError(
                    self.env._(
                        "Cannot reduce the capacity of %(link)s to %(capacity)s: a booked interval holds "
                        "%(samples)s samples. Adjust its bookings first.",
                        link=link.display_name,
                        capacity=link.capacity,
                        samples=len(samples),
                    )
                )
