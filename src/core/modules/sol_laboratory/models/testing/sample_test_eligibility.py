from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_SAMPLE_HANDOVER,
    MODEL_SAMPLE_TEST,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestEligibilityBase
else:
    SampleTestEligibilityBase = object


# Chỉ Tiêu Của Mẫu: whether a sample test can be booked.
class SampleTestEligibility(models.Model, SampleTestEligibilityBase):
    _inherit = MODEL_SAMPLE_TEST

    def _booking_refusal(self):
        """Why the test cannot be booked now; empty when it can. Its sample must be received by the department testing
        it and not be on hold, and the test must not be cancelled."""
        self.ensure_one()
        test = self.sudo()
        if test.status == "cancelled":
            return self.env._("%s is cancelled.", test.display_name)
        if test.sample_id.status == "on_hold":
            return self.env._("%s waits for more sample: its sample is on hold.", test.display_name)
        department = test._tested_by()
        received = department and self.env[MODEL_SAMPLE_HANDOVER].sudo().search_count(
            Domain("sample_id", "=", test.sample_id.id)
            & Domain("department_id", "=", department.id)
            & Domain("received_at", "!=", False),
            limit=1,
        )
        if not received:
            return self.env._("%s waits until its department receives its sample.", test.display_name)
        return ""

    def _check_bookable(self):
        for test in self:
            refusal = test._booking_refusal()
            if refusal:
                raise UserError(refusal)

    def action_schedule(self):
        self._check_bookable()
        for test in self:
            assignee = test._testing_task().assignee_id
            if assignee:
                self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(assignee, test.parameter_id)
        return super().action_schedule()

    def _compute_recommendation(self):
        """Only a bookable test is recommended a slot, and only to an assignee authorized for its parameter."""
        authorizations = self.env[MODEL_PARAMETER_AUTHORIZATION]
        bookable = self.filtered(
            lambda test: (
                not test._booking_refusal()
                and authorizations._authorized(test._testing_task().assignee_id, test.parameter_id)
            )
        )
        result = super(SampleTestEligibility, bookable)._compute_recommendation()
        (self - bookable).update(
            {
                "recommended_method_id": False,
                "recommended_machine_id": False,
                "recommended_start": False,
                "recommended_end": False,
            }
        )
        return result
