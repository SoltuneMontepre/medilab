from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_STOCK_MOVE
from odoo.addons.sol_inventory.constants.xml_ids import VALUE_GROUPS


# Dịch Chuyển Kho
class StockMove(models.Model):
    _inherit = MODEL_STOCK_MOVE

    # Value of the move from Odoo's costing, seen by those who see the value of stock.
    value = fields.Monetary(groups=VALUE_GROUPS)
    # Cost of one unit of the item moved, from the move's value.
    unit_cost = fields.Monetary(
        string="Unit Cost", currency_field="company_currency_id", compute="_compute_unit_cost", groups=VALUE_GROUPS
    )

    @api.depends("value", "quantity")
    def _compute_unit_cost(self):
        for move in self:
            quantity = move._get_valued_qty()
            move.unit_cost = abs(move.value) / quantity if quantity else 0.0

    def _get_value_from_quotation(self, quantity):
        # Odoo values stock that comes in without an order line at the item's cost. A receipt without a purchase order
        # carries the price typed on it, and a prepared solution what its ingredients cost; they are valued at it.
        data = super()._get_value_from_quotation(quantity)
        if data["quantity"] or self.purchase_line_id or not self.price_unit or not self.is_in:
            return data
        return {
            "value": self.price_unit * quantity,
            "quantity": quantity,
            "description": self.env._(
                "%(quantity)s %(unit)s at %(price)s each",
                quantity=quantity,
                unit=self.product_id.uom_id.name,
                price=self.company_currency_id.format(self.price_unit),
            ),
        }
