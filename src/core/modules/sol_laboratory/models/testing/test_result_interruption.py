from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.approvals import STATE_NONE
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_RESULT

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_test_result as TestResultInterruptionBase
else:
    TestResultInterruptionBase = object

# Fields only the system and the head's assessment set.
INTERRUPTION_FIELDS = frozenset({"is_interrupted", "interruption_assessment"})


# Kết Quả Thử Nghiệm: a measurement a machine failure ended, and the head of department's assessment of it.
class TestResultInterruption(models.Model, TestResultInterruptionBase):
    _inherit = MODEL_TEST_RESULT

    if not TYPE_CHECKING:
        # True when the machine broke down or lost calibration during the booking, so the result keeps the data
        # recorded until then.
        is_interrupted = fields.Boolean(string="Interrupted", readonly=True)
        # The head of department's assessment of an interrupted result; empty until assessed and for a result not
        # interrupted.
        interruption_assessment = fields.Selection(
            [("usable", "Usable"), ("retest", "Retest Needed"), ("more_sample", "More Sample Needed")],
            string="Assessment",
            readonly=True,
        )
        # True when the current user heads the department that tested the interrupted result, which they assess until
        # it is sent.
        can_assess_interruption = fields.Boolean(compute="_compute_can_assess_interruption")

    @api.depends_context("uid")
    @api.depends("is_interrupted", "status")
    def _compute_can_assess_interruption(self):
        for result in self:
            result.can_assess_interruption = (
                result.is_interrupted
                and result.status == STATE_NONE
                and self.env.user in result.sudo().sample_test_id._tested_by().manager_id.user_id
            )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                for name in INTERRUPTION_FIELDS:
                    vals.pop(name, None)
        return super().create(vals_list)

    def write(self, vals):
        if INTERRUPTION_FIELDS & set(vals) and not self.env.su:
            raise UserError(self.env._("The head of department assesses an interrupted result with its buttons."))
        return super().write(vals)

    def action_assess_usable(self):
        self._assess("usable")

    def action_assess_retest(self):
        self._assess("retest")

    def action_assess_more_sample(self):
        self._assess("more_sample")

    def _assess(self, assessment):
        for result in self:
            if not result.can_assess_interruption:
                raise UserError(
                    self.env._(
                        "Only the head of the department that tested %s assesses it, while it is interrupted and not "
                        "sent.",
                        result.display_name,
                    )
                )
        self.sudo().interruption_assessment = assessment

    def action_sign(self):
        self.ensure_one()
        if self.is_interrupted and self.status == STATE_NONE and self.interruption_assessment != "usable":
            raise UserError(
                self.env._("An interrupted result is sent only once the head of department assesses it as usable.")
            )
        return super().action_sign()
