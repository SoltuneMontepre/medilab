from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_inventory.constants.costs import KEEP_DONE_VALUES
from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT

if TYPE_CHECKING:
    from medilab_model_types import Model_product_product as ProductProductBase
else:
    ProductProductBase = object


# Vật Tư
class ProductProduct(models.Model, ProductProductBase):
    _inherit = MODEL_PRODUCT

    def _correct_inventory_valuation(self, from_date):
        # Odoo values every move again under the new costing method from the last closing, and MediLab never closes
        # the stock valuation. A change of costing method applies to the moves done after it.
        if self.env.context.get(KEEP_DONE_VALUES):
            return None
        return super()._correct_inventory_valuation(from_date)
