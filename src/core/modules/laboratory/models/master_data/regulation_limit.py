from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.laboratory.constants.models import (
    MODEL_MEASUREMENT_UNIT,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_TEST_PARAMETER,
)


# Giới Hạn Quy Chuẩn
class RegulationLimit(models.Model):
    _name = MODEL_REGULATION_LIMIT
    _description = "Regulation Limit"
    _order = "regulation_id, id"

    # The regulation that sets the limit.
    regulation_id = fields.Many2one(MODEL_REGULATION, required=True, ondelete="cascade")
    # The parameter the limit applies to.
    parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict", index=True)
    # The unit of the minimum and maximum; empty for a text-only limit.
    unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, ondelete="restrict")
    # Lowest allowed value; 0 when there is no lower limit.
    min_value = fields.Float(string="Minimum", digits=0)
    # Highest allowed value; 0 when there is no upper limit.
    max_value = fields.Float(string="Maximum", digits=0)
    # Decimals the limit shows on the report, such as 2 for 0.50.
    decimals = fields.Integer()
    # The limit as printed on the report when it is not a number, such as "Not detected", in each language.
    limit_text = fields.Char(translate=True)

    _regulation_parameter_unique = models.Constraint(
        "UNIQUE(regulation_id, parameter_id)", "A regulation sets at most one limit per parameter."
    )

    @api.depends("regulation_id", "parameter_id")
    def _compute_display_name(self):
        for limit in self:
            limit.display_name = f"{limit.regulation_id.code} – {limit.parameter_id.name}"

    def _in_use_domain(self):
        # A limit keeps its unit and parameter in use while its regulation is active.
        return Domain("regulation_id.active", "=", True)

    @api.constrains("min_value", "max_value", "limit_text", "unit_id")
    def _check_limit(self):
        for limit in self:
            if not (limit.min_value or limit.max_value or limit.limit_text):
                raise ValidationError(
                    self.env._(
                        "The limit for %s needs a minimum, a maximum or a text.", limit.parameter_id.display_name
                    )
                )
            if (limit.min_value or limit.max_value) and not limit.unit_id:
                raise ValidationError(
                    self.env._(
                        "The limit for %s needs a unit for its minimum or maximum.", limit.parameter_id.display_name
                    )
                )
            if limit.min_value and limit.max_value and limit.min_value > limit.max_value:
                raise ValidationError(
                    self.env._("The minimum of the limit for %s is above its maximum.", limit.parameter_id.display_name)
                )
