from odoo import api, models

from odoo.addons.sol_inventory.constants.costs import KEEP_DONE_VALUES
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_PRODUCT_CATEGORY
from odoo.addons.sol_inventory.constants.settings import COSTING_FIFO, ODOO_COST_METHODS
from odoo.addons.sol_inventory.constants.xml_ids import STOCK_ITEM_CATEGORY
from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN


# Danh Mục Sản Phẩm
class ProductCategory(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_PRODUCT_CATEGORY
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_PRODUCT_CATEGORY, MODEL_ARCHIVE_MIXIN]

    @api.model
    def _apply_costing_method(self, method):
        """Cost the stock items with this costing method from now on. Moves already done keep their value. Under first
        in, first out each lot keeps its own cost; switching to moving average starts each item's average cost at the
        value its stock had."""
        category = self.env.ref(STOCK_ITEM_CATEGORY).sudo().with_context(**{KEEP_DONE_VALUES: True})
        cost_method = ODOO_COST_METHODS[method]
        if category.property_cost_method == cost_method:
            return
        items = (
            category.env[MODEL_PRODUCT]
            .with_context(active_test=False)
            .search([("categ_id", "=", category.id), ("is_storable", "=", True)])
        )
        costs = {}
        if method != COSTING_FIFO:
            # Odoo's average of the stock it values, stock in transit included.
            costs = {
                item: item.avg_cost
                for item in items
                if item.uom_id.compare(item._with_valuation_context().qty_available, 0) > 0
            }
        category.property_cost_method = cost_method
        items._sync_lot_valuation()
        for item, cost in costs.items():
            item.standard_price = cost
