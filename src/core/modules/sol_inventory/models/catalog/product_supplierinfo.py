from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Mặt Hàng Nhà Cung Cấp
class ProductSupplierinfo(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_SUPPLIER_INFO
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SUPPLIER_INFO, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")

    # The item sold; its supplier lines are looked up by it.
    product_id = fields.Many2one(index=True)

    _supplier_item_unique = models.Constraint(
        "UNIQUE(partner_id, product_id)", "The supplier already sells this item; change its line instead."
    )

    def _get_filtered_supplier(self, company_id, product_id, params=False):
        # Odoo offers the prices of every active contact; an archived supplier keeps its contact and its prices, which
        # stay on record but are no longer offered.
        sellers = super()._get_filtered_supplier(company_id, product_id, params)
        contacts = sellers.partner_id.sudo().with_context(active_test=False)
        archived = contacts.supplier_ids.filtered(lambda supplier: not supplier.active).partner_id
        return sellers.filtered(lambda seller: seller.partner_id not in archived)
