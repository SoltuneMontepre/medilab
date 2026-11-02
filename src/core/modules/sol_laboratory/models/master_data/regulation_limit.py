from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PERMISSION_MIXIN,
    MODEL_REGULATION,
    MODEL_REGULATION_LIMIT,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_regulation_limit as RegulationLimitBase
else:
    RegulationLimitBase = object


# Giới Hạn Quy Chuẩn
class RegulationLimit(models.Model, RegulationLimitBase):
    _name = MODEL_REGULATION_LIMIT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Regulation Limit"
    _order = "regulation_id, id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The regulation that sets the limit.
        regulation_id = fields.Many2one(MODEL_REGULATION, required=True, ondelete="cascade")
        # The parameter the limit applies to.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="restrict", index=True)
        # The unit of the minimum and maximum; empty for a text-only limit.
        unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, ondelete="restrict", index=True)
        # True when a minimum is set. The minimum itself may be 0.
        min_set = fields.Boolean(string="Has a minimum")
        # Lowest allowed value, including 0. Meaningful when a minimum is set.
        min_value = fields.Float(string="Minimum", digits=0)
        # True when a maximum is set. The maximum itself may be 0.
        max_set = fields.Boolean(string="Has a maximum")
        # Highest allowed value, including 0. Meaningful when a maximum is set.
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

    @api.constrains("min_set", "max_set", "min_value", "max_value", "limit_text", "unit_id")
    def _check_limit(self):
        for limit in self:
            if not (limit.min_set or limit.max_set or limit.limit_text):
                raise ValidationError(
                    self.env._(
                        "The limit for %s needs a minimum, a maximum or a text.", limit.parameter_id.display_name
                    )
                )
            if (limit.min_set or limit.max_set) and not limit.unit_id:
                raise ValidationError(
                    self.env._(
                        "The limit for %s needs a unit for its minimum or maximum.", limit.parameter_id.display_name
                    )
                )
            if limit.min_set and limit.max_set and limit.min_value > limit.max_value:
                raise ValidationError(
                    self.env._("The minimum of the limit for %s is above its maximum.", limit.parameter_id.display_name)
                )
