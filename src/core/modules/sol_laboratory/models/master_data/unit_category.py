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
    from medilab_model_types import Model_medilab_unit_category as UnitCategoryBase
else:
    UnitCategoryBase = object


# Nhóm Đơn Vị
class UnitCategory(models.Model, UnitCategoryBase):
    _name = MODEL_UNIT_CATEGORY
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Unit Category"
    _order = "name"
    _permission_actions = ("create", "edit", "archive", "delete")

    if not TYPE_CHECKING:
        # Category name in each language, such as mass concentration in liquid.
        name = fields.Char(required=True, translate=True)
        # False when the category is archived.
        active = fields.Boolean(default=True)
        # Units in the category.
        unit_ids = fields.One2many(MODEL_MEASUREMENT_UNIT, "category_id", string="Units")
