from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_product_supplierinfo as ProductSupplierinfoBase
else:
    ProductSupplierinfoBase = object


# Mặt Hàng Nhà Cung Cấp
class ProductSupplierinfo(models.Model, ProductSupplierinfoBase):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_SUPPLIER_INFO
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SUPPLIER_INFO, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
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

    @api.model
    def _record_last_price(self, partner, item, price):
        """Keep the price of one unit of the item, excluding VAT, the supplier was last paid on its line for the item."""
        line = self.sudo().search(Domain("partner_id", "=", partner.id) & Domain("product_id", "=", item.id), limit=1)
        if line:
            line.price = price
        else:
            line.create(
                {
                    "partner_id": partner.id,
                    "product_id": item.id,
                    "product_tmpl_id": item.product_tmpl_id.id,
                    "price": price,
                }
            )
