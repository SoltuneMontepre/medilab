from odoo import fields, models
from odoo.addons.laboratory.constants.models import MODEL_TEST_PARAMETER

# Chỉ Tiêu
class TestParameter(models.Model):
    _name = MODEL_TEST_PARAMETER
    _description = "Test Parameters"
    _order = "code"

    code = fields.Char(required=True)
    name = fields.Char(required=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a test parameter must be unique.")
