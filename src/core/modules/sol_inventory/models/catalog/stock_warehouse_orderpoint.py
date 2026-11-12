from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_inventory.constants.models import MODEL_ORDERPOINT
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_stock_warehouse_orderpoint as StockWarehouseOrderpointBase
else:
    StockWarehouseOrderpointBase = object


# Tồn Tối Thiểu
class StockWarehouseOrderpoint(models.Model, StockWarehouseOrderpointBase):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_ORDERPOINT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ORDERPOINT, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")
