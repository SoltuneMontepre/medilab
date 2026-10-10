from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.commerce.constants.models import MODEL_SUBCONTRACT_COST, MODEL_VND_MIXIN
from odoo.addons.laboratory.constants.models import MODEL_PARAMETER_METHOD, MODEL_PERMISSION_MIXIN


# Chi Phí Thầu Phụ
class SubcontractCost(models.Model):
    _name = MODEL_SUBCONTRACT_COST
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_VND_MIXIN]
    _description = "Subcontract Cost"
    _order = "parameter_method_id"
    _rec_name = "parameter_method_id"

    # The subcontracted parameter and method pair.
    parameter_method_id = fields.Many2one(
        MODEL_PARAMETER_METHOD,
        required=True,
        ondelete="cascade",
        domain=[("subcontractor_id", "!=", False)],
        string="Way of Testing",
    )
    # Cost of one test, excluding VAT.
    cost = fields.Monetary(required=True)
    # False when the cost is archived.
    active = fields.Boolean(default=True)

    _parameter_method_unique = models.Constraint(
        "UNIQUE(parameter_method_id)", "A subcontracted way of testing has only one cost."
    )
    _cost_positive = models.Constraint("CHECK(cost >= 0)", "A cost cannot be negative.")

    @api.constrains("parameter_method_id")
    def _check_subcontracted(self):
        in_house = self.parameter_method_id.filtered(lambda pair: not pair.subcontractor_id)
        if in_house:
            raise ValidationError(
                self.env._("%s is tested in-house, so it has no subcontract cost.", in_house[0].display_name)
            )
