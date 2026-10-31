from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_MEASUREMENT_UNIT,
    MODEL_PERMISSION_MIXIN,
    MODEL_UNIT_CATEGORY,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_measurement_unit as MeasurementUnitBase
else:
    MeasurementUnitBase = object


# Đơn Vị Đo
class MeasurementUnit(models.Model, MeasurementUnitBase):
    _name = MODEL_MEASUREMENT_UNIT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Measurement Unit"
    _order = "name"
    _permission_actions = ("create", "edit", "archive", "delete")

    if not TYPE_CHECKING:
        # Unique unit symbol, such as mg/kg.
        name = fields.Char(required=True)
        # The kind of quantity the unit measures; units convert only within one category.
        category_id = fields.Many2one(MODEL_UNIT_CATEGORY, required=True, ondelete="restrict", index=True)
        # Number of reference units in one of this unit, such as 0.001 for ug/L when mg/L is the reference; 1 for the reference unit.
        factor = fields.Float(required=True, default=1, digits=0)
        # False when the unit is archived.
        active = fields.Boolean(default=True)

    _name_unique = models.Constraint("UNIQUE(name)", "A measurement unit with this symbol already exists.")
    _factor_positive = models.Constraint("CHECK(factor > 0)", "The factor of a unit must be greater than zero.")
