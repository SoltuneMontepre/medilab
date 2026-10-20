from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import MODEL_ORDERPOINT, MODEL_STOCK_LOCATION
from odoo.addons.sol_inventory.constants.notifications import EVENT_BELOW_MINIMUM
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN, MODEL_MAIL_MESSAGE, MODEL_PERMISSION_MIXIN


# Tồn Tối Thiểu
class StockWarehouseOrderpoint(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_ORDERPOINT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_ORDERPOINT, MODEL_PERMISSION_MIXIN]
    _permission_actions = ("create", "edit", "delete")

    # The vendor price a suggested purchase uses; the prices of archived suppliers stay on record but are not offered.
    supplier_id = fields.Many2one(
        domain="['|', ('product_id', '=', product_id), '&', ('product_id', '=', False), "
        "('product_tmpl_id', '=', product_tmpl_id), ('supplier_archived', '=', False)]"
    )

    def _compute_qty(self):
        result = super()._compute_qty()
        # Odoo counts the stores below a store in its stock. A store's minimum is about the stock it holds itself: the
        # stores below it hold stock already issued to them.
        stores_below = {}
        for minimum in self.filtered(lambda minimum: minimum.product_id and minimum.location_id):
            location = minimum.location_id
            if location not in stores_below:
                stores_below[location] = location._stores_below()
            below = stores_below[location]
            if not below:
                continue
            item = minimum.product_id.with_context(minimum._get_product_context(), location=below.ids)
            minimum.qty_on_hand -= item.qty_available
            minimum.qty_forecast -= item.virtual_available
        return result

    def _get_qty_to_order(self, qty_in_progress_by_orderpoint=None):
        self.ensure_one()
        below = self.location_id._stores_below()
        if not below:
            return super()._get_qty_to_order(qty_in_progress_by_orderpoint)
        # Odoo forecasts the quantity to order again with the stores below counted in; the store's own stock is meant.
        if self.uom_id.compare(self.qty_forecast, self.product_min_qty) >= 0:
            return 0.0
        qty_in_progress = (qty_in_progress_by_orderpoint or {}).get(self.id)
        if qty_in_progress is None:
            qty_in_progress = self._quantity_in_progress()[self.id]
        context = self._get_product_context()
        forecast = (
            self.product_id.with_context(context).virtual_available
            - self.product_id.with_context(context, location=below.ids).virtual_available
        )
        target = max(self.product_min_qty, self.product_max_qty)
        return self._get_multiple_rounded_qty(target - forecast - qty_in_progress)

    def _get_orderpoint_action(self):
        # Replenishment buys for the central store, where purchases are received; a store below it gets stock through a
        # requisition.
        action = super()._get_orderpoint_action()
        action["domain"] = [("location_id", "not in", self._lower_store_locations().ids)]
        return action

    def action_replenish(self):
        lower = self._lower_store_locations()
        refused = self.filtered(lambda minimum: minimum.location_id in lower)
        if refused:
            raise UserError(
                self.env._(
                    "Purchases are received at the central store. %s gets stock through a requisition.",
                    format_list(self.env, refused.sudo().location_id.mapped("display_name")),
                )
            )
        return super().action_replenish()

    def _lower_store_locations(self):
        """The stores below the central store and the locations inside them."""
        locations = self.env[MODEL_STOCK_LOCATION]
        lower = locations._central_stores()._stores_below()
        return locations.sudo().search([("id", "child_of", lower.ids)]) if lower else locations

    def _warn_if_below(self, taken, key):
        """Warn the manager of the store when taking this quantity of the item took its stock below the minimum."""
        self.ensure_one()
        item = self.product_id
        self.invalidate_recordset(["qty_on_hand"])
        held = self.qty_on_hand
        minimum = self.product_min_qty
        if item.uom_id.compare(held, minimum) >= 0 or item.uom_id.compare(held + taken, minimum) < 0:
            return
        body = self.env._(
            "%(store)s holds %(held)s %(unit)s of %(item)s, below its minimum of %(minimum)s %(unit)s.",
            store=self.location_id.display_name,
            held=item.uom_id.round(held),
            minimum=item.uom_id.round(minimum),
            unit=item.uom_id.name,
            item=item.display_name,
        )
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_BELOW_MINIMUM, self, key, body, partners=self.location_id._manager_partners()
        )
