from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_TEST_REQUEST

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestPlanBase
else:
    TestRequestPlanBase = object


# Yêu Cầu Thử Nghiệm: a changed committed return date recalculates the plans of the departments testing its samples.
class TestRequestPlan(models.Model, TestRequestPlanBase):
    _inherit = MODEL_TEST_REQUEST

    def write(self, vals):
        result = super().write(vals)
        if "expected_date" in vals:
            bookings = self.sudo().sample_ids.test_ids.booking_ids
            self.env[MODEL_MACHINE_BOOKING]._plan(bookings.department_id)
        return result
