from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_MEASUREMENT_UNIT, MODEL_UNIT_CATEGORY


# Nhóm Đơn Vị
class UnitCategory(models.Model):
    _name = MODEL_UNIT_CATEGORY
    _inherit = [MODEL_ARCHIVE_MIXIN]
    _description = "Unit Category"
    _order = "name"

    # Category name in each language, such as mass concentration in liquid.
    name = fields.Char(required=True, translate=True)
    # False when the category is archived.
    active = fields.Boolean(default=True)
    # Units in the category.
    unit_ids = fields.One2many(MODEL_MEASUREMENT_UNIT, "category_id", string="Units")
