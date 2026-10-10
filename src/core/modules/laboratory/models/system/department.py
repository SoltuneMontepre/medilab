from odoo import fields, models

from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_DEPARTMENT, MODEL_PERMISSION_MIXIN


# Phòng Ban
class Department(models.Model):
    _name = MODEL_DEPARTMENT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    _description = "Department"
    _order = "name"

    # Department name.
    name = fields.Char(required=True)
    # False when the department is archived.
    active = fields.Boolean(default=True)
