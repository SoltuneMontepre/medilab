from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_inventory.constants.models import (
    MODEL_STOCK_MOVE,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.stock import INTERNAL_USAGE, LOT_AVAILABLE, LOT_EXPIRED
from odoo.addons.sol_inventory.constants.xml_ids import SCRAP_EXPIRED, VALUE_GROUPS
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION_MIXIN, MODEL_RES_CONFIG_SETTINGS

# Odoo's own access each action stands for; quants change with every move under Odoo's accesses.
ODOO_OPERATIONS = {"read": "read", "create": "create", "edit": "write", "archive": "write", "delete": "unlink"}
# The last day the quant's container can be used.
CONTAINER_USABLE_UNTIL = "package_id.usable_until"


# Tồn Kho
class StockQuant(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_QUANT
    _inherit = [MODEL_STOCK_QUANT, MODEL_PERMISSION_MIXIN]
    # Reading the stock on hand and its value. Quants change only through moves.
    _permission_actions = ("read",)

    # Value of the stock, from Odoo's costing.
    value = fields.Monetary(groups=VALUE_GROUPS)
    # Currency of the value.
    currency_id = fields.Many2one(groups=VALUE_GROUPS)
    # Last day the stock can be used: its container's usable date, or its lot's expiry.
    usable_until = fields.Date(string="Usable Until", compute="_compute_usable_until")
    # True for stock past its usable date: in a lot that expired, or in a container whose usable date has passed.
    expired = fields.Boolean(compute="_compute_expiry", search="_search_expired")
    # True for stock usable for fewer days than the expiry warning.
    expiring_soon = fields.Boolean(string="Expiring Soon", compute="_compute_expiry", search="_search_expiring_soon")

    @api.depends(CONTAINER_USABLE_UNTIL, "lot_id.expiration_date")
    def _compute_usable_until(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        for quant in self:
            quant.usable_until = quant.package_id.usable_until or packages._as_date(quant.lot_id.expiration_date)

    def _compute_expiry(self):
        expired = self.filtered_domain(self._expired_domain())
        expiring = self.filtered_domain(self._expiring_domain())
        for quant in self:
            quant.expired = quant in expired
            quant.expiring_soon = quant in expiring

    def _search_expired(self, operator, value):
        if operator != "in" or True not in value:
            return NotImplemented
        return self._expired_domain()

    def _search_expiring_soon(self, operator, value):
        if operator != "in" or True not in value:
            return NotImplemented
        return self._expiring_domain()

    def _has_permission(self, action):
        if action == "read":
            return super()._has_permission(action)
        return self.has_access(ODOO_OPERATIONS[action])

    def _check_permission(self, action):
        if action == "read":
            return super()._check_permission(action)
        return self.check_access(ODOO_OPERATIONS[action])

    def _get_inventory_move_values(self, qty, location_id, location_dest_id, package_id=False, package_dest_id=False):
        values = super()._get_inventory_move_values(qty, location_id, location_dest_id, package_id, package_dest_id)
        # A correction names its reason as the adjustment's name.
        reason = self.env.context.get("inventory_name")
        if reason:
            values["reason"] = reason
        return values

    @api.model
    def _expired_domain(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        today = packages._today()
        return (
            Domain("location_id.usage", "=", INTERNAL_USAGE)
            & Domain("quantity", ">", 0)
            & (
                Domain("lot_id.status", "=", LOT_EXPIRED)
                | Domain("lot_id.expiration_date", "<", packages._at_utc(today))
                | Domain(CONTAINER_USABLE_UNTIL, "<", today)
            )
        )

    @api.model
    def _expiring_domain(self):
        packages = self.env[MODEL_STOCK_PACKAGE]
        today = packages._today()
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("expiry_warning_days")
        lot_expiring = (
            Domain("lot_id.status", "=", LOT_AVAILABLE)
            & Domain("lot_id.alert_date", "<", packages._at_utc(today + timedelta(days=1)))
            & Domain("lot_id.expiration_date", ">=", packages._at_utc(today))
        )
        container_expiring = Domain(CONTAINER_USABLE_UNTIL, ">=", today) & Domain(
            CONTAINER_USABLE_UNTIL, "<=", today + timedelta(days=days)
        )
        return (
            Domain("location_id.usage", "=", INTERNAL_USAGE)
            & Domain("quantity", ">", 0)
            & (lot_expiring | container_expiring)
        )

    def action_dispose(self):
        """Move what remains of this expired stock to the scrap location with the reason Expired. A container left
        empty is disposed of, and so is a lot with nothing left anywhere."""
        moves = self.env[MODEL_STOCK_MOVE]
        moves._check_can_create(self.env._("You are not allowed to dispose of stock."))
        quants = self.sudo().exists()
        expired = quants.filtered_domain(self._expired_domain())
        if quants - expired:
            raise UserError(
                self.env._(
                    "Only expired stock is disposed of, not: %s.",
                    format_list(self.env, (quants - expired).mapped(lambda quant: quant._stock_name())),
                )
            )
        quants.location_id.with_env(self.env)._check_kept_by_user()
        tag = self.env.ref(SCRAP_EXPIRED)
        # Read before the moves, which may delete the emptied quants.
        lots = quants.lot_id
        takes = defaultdict(list)
        for quant in quants:
            takes[quant.product_id].append(
                {
                    "location": quant.location_id,
                    "quantity": quant.quantity,
                    "lot": quant.lot_id,
                    "package": quant.package_id,
                }
            )
        for item, item_takes in takes.items():
            moves._done_moves(
                item, item_takes, moves._destination(item, True), scrap=True, scrap_reason_tag_ids=tag, automatic=False
            )
        lots._settle_disposed()
        return True

    def _stock_name(self):
        self.ensure_one()
        parts = [self.product_id.display_name, self.lot_id.name, self.package_id.name, self.location_id.display_name]
        return " / ".join(part for part in parts if part)
