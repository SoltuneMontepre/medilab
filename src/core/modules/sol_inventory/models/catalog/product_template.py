from odoo import api, models

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

# Template fields that change how an item's stock is counted.
TRACKING_FIELDS = ("tracking", "is_storable", "store_by")


# Sản Phẩm
class ProductTemplate(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_PRODUCT_TEMPLATE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PRODUCT_TEMPLATE]

    def write(self, vals):
        # Odoo's own product form changes the tracking on the template, past the item's checks.
        if not set(TRACKING_FIELDS) & vals.keys():
            return super().write(vals)
        items = self.product_variant_ids.filtered("item_kind")
        tracking_before = items._item_trackings()
        result = super().write(vals)
        items._check_tracking_kept(tracking_before)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_stock_item(self):
        # Deleting a template deletes its variants in the database, past the item's own check.
        self.with_context(active_test=False).product_variant_ids._unlink_except_stock_item()
