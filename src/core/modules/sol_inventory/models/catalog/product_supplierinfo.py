from odoo import models

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Mặt Hàng Nhà Cung Cấp
class ProductSupplierinfo(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_SUPPLIER_INFO
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SUPPLIER_INFO, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")

    _supplier_item_unique = models.Constraint(
        "UNIQUE(partner_id, product_id)", "The supplier already sells this item; change its line instead."
    )
