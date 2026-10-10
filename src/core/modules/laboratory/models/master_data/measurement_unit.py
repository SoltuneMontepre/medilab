from odoo import fields, models

from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_MEASUREMENT_UNIT, MODEL_UNIT_CATEGORY


# Đơn Vị Đo
class MeasurementUnit(models.Model):
    _name = MODEL_MEASUREMENT_UNIT
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Measurement Unit"
    _order = "name"

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
