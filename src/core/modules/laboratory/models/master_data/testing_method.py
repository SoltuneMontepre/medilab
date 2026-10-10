from odoo import fields, models

from odoo.addons.laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CHEMICAL,
    MODEL_TESTING_FIELD,
    MODEL_TESTING_METHOD,
)


# Phương Pháp Thử
class TestingMethod(models.Model):
    _name = MODEL_TESTING_METHOD
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Testing Method"
    _rec_name = "code"
    _order = "code"
    _rec_names_search = ("code", "name")

    # Unique standard reference of the method, such as TCVN 6187-1:2009.
    code = fields.Char(required=True, copy=False)
    # Title of the standard in each language, such as "Water quality — Detection of coliforms".
    name = fields.Char(required=True, translate=True)
    # The testing field the method belongs to.
    field_id = fields.Many2one(
        MODEL_TESTING_FIELD, required=True, ondelete="restrict", index=True, string="Testing Field"
    )
    # Chemicals the method uses.
    chemical_ids = fields.Many2many(
        MODEL_CHEMICAL,
        "medilab_chemical_method_rel",
        "method_id",
        "chemical_id",
        ondelete="restrict",
        string="Chemicals",
    )
    # False when the method is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a testing method must be unique.")
