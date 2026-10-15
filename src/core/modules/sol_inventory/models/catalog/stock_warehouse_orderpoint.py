from odoo import models

from odoo.addons.sol_inventory.constants.models import MODEL_ORDERPOINT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Tồn Tối Thiểu
class StockWarehouseOrderpoint(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_ORDERPOINT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ORDERPOINT, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "archive", "delete")
