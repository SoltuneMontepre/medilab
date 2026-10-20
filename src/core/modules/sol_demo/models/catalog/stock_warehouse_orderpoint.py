from odoo import api, models

from odoo.addons.sol_demo.models.purchasing.purchase_order import STOREKEEPER
from odoo.addons.sol_inventory.constants.models import MODEL_ORDERPOINT

MARKER = "sol_demo.demo_stock_warehouse_orderpoint_nitric_acid"
CENTRAL = "stock.stock_location_stock"
# The minimum and maximum quantity of each item in the central store.
MINIMUMS = (("nitric_acid", 1000, 5000), ("agar_plates", 50, 200), ("nitrile_gloves", 200, 1000))


# Tồn Tối Thiểu
class StockWarehouseOrderpoint(models.Model):
    _inherit = MODEL_ORDERPOINT

    @api.model
    def _seed_minimum_demo(self):
        """The minimum quantities of the central store, set by the storekeeper as the item form does. Odoo's
        Replenishment removes the manual minimums the system made once nothing is left to order. Safe to run again."""
        if self.env.ref(MARKER, raise_if_not_found=False):
            return
        central = self.env.ref(CENTRAL)
        minimums = (
            self.with_user(self.env.ref(STOREKEEPER))
            .sudo()
            .create(
                [
                    {
                        "product_id": self.env.ref(f"sol_demo.demo_product_product_{name}").id,
                        "location_id": central.id,
                        "trigger": "manual",
                        "product_min_qty": minimum,
                        "product_max_qty": maximum,
                    }
                    for name, minimum, maximum in MINIMUMS
                ]
            )
        )
        self.env["ir.model.data"]._update_xmlids(
            [
                {"xml_id": f"sol_demo.demo_stock_warehouse_orderpoint_{name}", "record": record, "noupdate": True}
                for (name, _minimum, _maximum), record in zip(MINIMUMS, minimums, strict=True)
            ]
        )
