from odoo import fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_ORDERPOINT
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
