from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_MACHINE_BOOKING, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_request as TestRequestPlanBase
else:
    TestRequestPlanBase = object


# Yêu Cầu Thử Nghiệm: the expected return date changes only through a recorded change with the customer's agreement,
# and a changed expected return date or priority recalculates the plans of the departments testing its samples.
class TestRequestPlan(models.Model, TestRequestPlanBase):
    _inherit = MODEL_TEST_REQUEST

    def write(self, vals):
        if "committed_date" in vals and not (self.env.su or self.env.context.get(CHANGING_COMMITTED_DATE)):
            raise UserError(self.env._("Change the expected return date with Change Return Date."))
        result = super().write(vals)
        if {"committed_date", "priority"} & set(vals):
            bookings = self.sudo().sample_ids.test_ids.booking_ids
            self.env[MODEL_MACHINE_BOOKING]._plan(bookings.department_id)
        return result
