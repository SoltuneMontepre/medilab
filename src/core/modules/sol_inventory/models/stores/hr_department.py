from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_LOCATION
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT

if TYPE_CHECKING:
    from medilab_model_types import Model_hr_department as HrDepartmentBase
else:
    HrDepartmentBase = object


# Phòng Ban
class HrDepartment(models.Model, HrDepartmentBase):
    _inherit = MODEL_DEPARTMENT

    if not TYPE_CHECKING:
        # Stores the department or team holds.
        store_ids = fields.One2many(MODEL_STOCK_LOCATION, "holder_id", string="Stores")

    @api.constrains("parent_id")
    def _check_held_stores(self):
        # Moving a team to another department moves its store away from the store of its department.
        self.sudo().store_ids._check_store_tree()
