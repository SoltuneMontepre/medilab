from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_TESTING_FIELD


# Lĩnh Vực Thử Nghiệm
class TestingField(models.Model):
    _name = MODEL_TESTING_FIELD
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Testing Field"
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the field.
    code = fields.Char(required=True, copy=False)
    # Field name in each language, such as Chemistry.
    name = fields.Char(required=True, translate=True)
    # False when the field is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a testing field must be unique.")
