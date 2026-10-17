from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_TESTING_METHOD,
    MODEL_TESTING_METHOD_STEP,
)


# Bước Phương Pháp Thử
class TestingMethodStep(models.Model):
    _name = MODEL_TESTING_METHOD_STEP
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Testing Method Step"
    _order = "method_id, sequence"
    _permission_actions = ("create", "edit", "delete")

    # The testing method the step belongs to.
    method_id = fields.Many2one(MODEL_TESTING_METHOD, string="Testing Method", required=True, ondelete="cascade")
    # Step number; steps are shown in this order.
    sequence = fields.Integer(string="Step", required=True)
    # Minutes the step takes.
    duration_minutes = fields.Integer(string="Minutes", required=True)
    # What to do in the step.
    instruction = fields.Text(required=True)
    # Remark on the step, such as a precaution.
    note = fields.Text()

    _method_sequence_unique = models.Constraint(
        "UNIQUE(method_id, sequence)", "Two steps of a testing method cannot have the same number."
    )
    _sequence_positive = models.Constraint("CHECK(sequence > 0)", "A step number must be 1 or more.")
    _duration_positive = models.Constraint("CHECK(duration_minutes > 0)", "A step takes at least one minute.")

    @api.depends("method_id", "sequence")
    def _compute_display_name(self):
        for step in self:
            step.display_name = f"{step.method_id.code} – {step.sequence}"

    @api.constrains("instruction")
    def _check_instruction(self):
        if any(not (step.instruction or "").strip() for step in self):
            raise ValidationError(self.env._("Say what to do in the step."))
