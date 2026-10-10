from odoo import fields, models

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_MEASUREMENT_UNIT,
    MODEL_SAMPLE_TYPE,
)


# Loại Mẫu
class SampleType(models.Model):
    _name = MODEL_SAMPLE_TYPE
    _inherit = [MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _description = "Sample Type"
    _parent_store = True
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the sample type, such as LM.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # Sample type name in each language.
    name = fields.Char(required=True, translate=True)
    # The broader sample type this one belongs to; empty for a top-level type.
    parent_id = fields.Many2one(MODEL_SAMPLE_TYPE, ondelete="restrict", index=True)
    # Ids of the sample type and all its ancestors, such as 2/7/, so filtering by a type finds its children in one query.
    parent_path = fields.Char(index=True)
    # Smallest amount of sample to collect, in the minimum quantity unit.
    minimum_quantity = fields.Float(digits=0)
    # Unit of the minimum amount, such as g or mL.
    minimum_quantity_unit_id = fields.Many2one(MODEL_MEASUREMENT_UNIT, ondelete="restrict")
    # How to collect the sample, in each language.
    sampling_requirements = fields.Text(translate=True)
    # How to store the sample before and after testing, such as "2-8 °C, away from light", in each language.
    storage_conditions = fields.Text(translate=True)
    # True when the laboratory keeps the sample after testing.
    is_retained = fields.Boolean(string="Retained After Testing")
    # Number of days the sample is kept after testing.
    retention_days = fields.Integer()
    # What to do with the sample right after testing, in each language.
    post_test_requirements = fields.Text(translate=True)
    # How to dispose of the sample after the retention period, in each language.
    disposal_method = fields.Text(translate=True)
    # False when the sample type is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a sample type must be unique.")
