from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER, MODEL_SUPPLIER_INFO
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_PERMISSION_MIXIN


# Mặt Hàng Nhà Cung Cấp
class ProductSupplierinfo(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_SUPPLIER_INFO
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_SUPPLIER_INFO, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")

    # The item sold; its supplier lines are looked up by it.
    product_id = fields.Many2one(index=True)
    # True when the supplier is archived: its prices stay on record but are no longer offered.
    supplier_archived = fields.Boolean(compute="_compute_supplier_archived", search="_search_supplier_archived")

    _supplier_item_unique = models.Constraint(
        "UNIQUE(partner_id, product_id)", "The supplier already sells this item; change its line instead."
    )

    def _compute_supplier_archived(self):
        archived = self._archived_contacts(self.partner_id)
        for line in self:
            line.supplier_archived = line.partner_id in archived

    def _search_supplier_archived(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        wanted = (True in value) == (operator == "in")
        return Domain("partner_id", "in" if wanted else "not in", self._archived_contacts().ids)

    @api.model
    def _archived_contacts(self, contacts=None):
        """The company contacts of archived suppliers, among these contacts when given."""
        domain = [("active", "=", False)]
        if contacts is not None:
            domain.append(("partner_id", "in", contacts.ids))
        return self.env[MODEL_SUPPLIER].sudo().with_context(active_test=False).search(domain).partner_id

    def _get_filtered_supplier(self, company_id, product_id, params=False):
        # Odoo offers the prices of every active contact; an archived supplier keeps its contact and its prices, which
        # stay on record but are no longer offered.
        sellers = super()._get_filtered_supplier(company_id, product_id, params)
        archived = self._archived_contacts(sellers.partner_id)
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
