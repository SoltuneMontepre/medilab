from typing import TYPE_CHECKING

from odoo import api, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_SAMPLE_TEST,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_machine_booking as MachineBookingEligibilityBase
else:
    MachineBookingEligibilityBase = object


# Lịch Đặt Máy: only a bookable sample test is booked, and only for a person authorized to test its parameter.
class MachineBookingEligibility(models.Model, MachineBookingEligibilityBase):
    _inherit = MODEL_MACHINE_BOOKING

    @api.model_create_multi
    def create(self, vals_list):
        # Scheduling books as superuser once the sample test's action checked it.
        if not self.env.su:
            test_ids = [vals["sample_test_id"] for vals in vals_list if vals.get("sample_test_id")]
            self.env[MODEL_SAMPLE_TEST].browse(test_ids)._check_bookable()
        return super().create(vals_list)

    @api.constrains("person_id", "sample_test_id")
    def _check_person_authorized(self):
        for booking in self.filtered("person_id"):
            self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(
                booking.person_id, booking.sudo().sample_test_id.parameter_id
            )
