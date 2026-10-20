from odoo import api, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT_TEMPLATE
from odoo.addons.sol_inventory.constants.xml_ids import STOCK_ITEM_CATEGORY
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

# Template fields that change how an item's stock is counted.
TRACKING_FIELDS = ("tracking", "is_storable", "store_by")
# Template fields the item's rules check: how its stock is counted and whether it is bought.
ITEM_RULE_FIELDS = (*TRACKING_FIELDS, "purchase_ok")


# Sản Phẩm
class ProductTemplate(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_PRODUCT_TEMPLATE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PRODUCT_TEMPLATE]

    def write(self, vals):
        if "categ_id" in vals and vals["categ_id"] != self.env.ref(STOCK_ITEM_CATEGORY).id:
            items = self.product_variant_ids.filtered("item_kind")
            if items:
                raise UserError(
                    self.env._(
                        "Stock items stay in their own category, whose costing method follows the costing setting: %s.",
                        format_list(self.env, items.mapped("display_name")),
                    )
                )
        # Odoo's own product form changes the tracking, and whether the product is bought, on the template, past the
        # item's checks.
        checked = set(ITEM_RULE_FIELDS) & vals.keys()
        if not checked:
            return super().write(vals)
        items = self.product_variant_ids.filtered("item_kind")
        tracking_before = items._item_trackings()
        result = super().write(vals)
        items._check_tracking_kept(tracking_before)
        items._sync_lot_valuation()
        # The item's own constraints, such as the tracking its kind or its recipes need, or a prepared solution never
        # being bought.
        items._validate_fields(checked)
        return result

    @api.ondelete(at_uninstall=False)
    def _unlink_except_stock_item(self):
        # Deleting a template deletes its variants in the database, past the item's own check.
        self.with_context(active_test=False).product_variant_ids._unlink_except_stock_item()
