from datetime import timedelta

from lxml import etree

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import format_date, format_list

from odoo.addons.sol_inventory.constants.jobs import EXPIRED
from odoo.addons.sol_inventory.constants.models import (
    MODEL_PRODUCT,
    MODEL_PURCHASE_ORDER,
    MODEL_STOCK_LOT,
    MODEL_STOCK_PACKAGE,
    MODEL_STOCK_PICKING,
    MODEL_STOCK_QUANT,
)
from odoo.addons.sol_inventory.constants.notifications import EVENT_STOCK_EXPIRED, EVENT_STOCK_EXPIRING
from odoo.addons.sol_inventory.constants.stock import INTERNAL_USAGE, LOT_AVAILABLE, LOT_DISPOSED, LOT_EXPIRED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_IR_ATTACHMENT,
    MODEL_MAIL_MESSAGE,
    MODEL_PERMISSION_MIXIN,
)

# Stat buttons of Odoo's lot form and the model of the documents each counts.
DOCUMENT_BUTTONS = {
    "action_view_po": MODEL_PURCHASE_ORDER,
    # Added by Odoo's sale_stock once E-commerce is installed too.
    "action_view_so": "sale.order",
    "action_lot_open_transfers": MODEL_STOCK_PICKING,
}


# Lô
class StockLot(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_LOT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_LOT, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]
    # Receipts create lots; the storekeeper corrects them or adds their certificate later.
    _permission_actions = ("edit",)

    # available, expired or disposed. An expired lot cannot be used.
    status = fields.Selection(
        [(LOT_AVAILABLE, "Available"), (LOT_EXPIRED, "Expired"), (LOT_DISPOSED, "Disposed")],
        required=True,
        default=LOT_AVAILABLE,
    )
    # The manufacturer's certificate that came with the lot.
    certificate_id = fields.Many2one(MODEL_IR_ATTACHMENT, string="Manufacturer's Certificate", ondelete="set null")

    _status_expiry_idx = models.Index("(status, expiration_date)")

    @api.model
    def _alert_date_exceeded(self):
        # Odoo schedules an activity for the person responsible for the product once a lot reaches its alert date.
        # MediLab notifies the managers of the stores holding the lots of its stock items itself.
        self.sudo().search(
            [
                ("product_id.item_kind", "!=", False),
                ("product_expiry_reminded", "=", False),
                ("alert_date", "<=", fields.Datetime.now()),
            ]
        ).product_expiry_reminded = True
        return super()._alert_date_exceeded()

    @api.model
    def _apply_expiry_warning(self, days):
        """List and notify lots this many days before they expire: product_expiry's alert time of every stock item, and
        the alert date of their lots that are still available."""
        items = (
            self.env[MODEL_PRODUCT]
            .sudo()
            .with_context(active_test=False)
            .search([("item_kind", "!=", False), ("alert_time", "!=", days)])
        )
        if not items:
            return
        items.product_tmpl_id.write({"alert_time": days})
        lots = self.sudo().search(
            [("product_id", "in", items.ids), ("status", "=", LOT_AVAILABLE), ("expiration_date", "!=", False)]
        )
        for lot in lots:
            alert = lot.expiration_date - timedelta(days=days)
            if lot.alert_date != alert:
                lot.alert_date = alert

    @api.model
    def _to_warn(self):
        """The available lots past their expiry date, those a disposal elsewhere already marked expired that still have
        stock left, and those with stock left that expire within the warning."""
        packages = self.env[MODEL_STOCK_PACKAGE]
        today = packages._today()
        start = packages._at_utc(today)
        expired = self.sudo().search([("status", "=", LOT_AVAILABLE), ("expiration_date", "<", start)])
        expired |= self.sudo().search([("status", "=", LOT_EXPIRED)])._held_quants().lot_id
        expiring = self.sudo().search(
            [
                ("status", "=", LOT_AVAILABLE),
                ("expiration_date", ">=", start),
                ("alert_date", "<", packages._at_utc(today + timedelta(days=1))),
            ]
        )
        return expired, expiring._held_quants().lot_id

    def _is_expired(self):
        self.ensure_one()
        packages = self.env[MODEL_STOCK_PACKAGE]
        return bool(self.expiration_date) and self.expiration_date < packages._at_utc(packages._today())

    def _held_quants(self):
        """The stock of these lots in the laboratory's own locations."""
        return (
            self.env[MODEL_STOCK_QUANT]
            .sudo()
            .search(
                Domain("lot_id", "in", self.ids)
                & Domain("quantity", ">", 0)
                & Domain("location_id.usage", "=", INTERNAL_USAGE)
            )
        )

    def _warn_expiry(self, kind):
        """Mark an expired lot expired, and notify the managers of the stores holding what is left of it that it
        expired or expires soon. A lot whose expiry was corrected meanwhile is left as it is; a lot a disposal already
        marked expired is still notified once."""
        self.ensure_one()
        lot = self.sudo()
        statuses = (LOT_AVAILABLE, LOT_EXPIRED) if kind == EXPIRED else (LOT_AVAILABLE,)
        if lot.status not in statuses or lot._is_expired() != (kind == EXPIRED):
            return
        if kind == EXPIRED:
            lot.status = LOT_EXPIRED
        quants = lot._held_quants()
        if not quants:
            return
        item = lot.product_id
        stores = quants.location_id._holding_stores()
        values = {
            "lot": lot.name,
            "item": item.display_name,
            "date": format_date(self.env, self.env[MODEL_STOCK_PACKAGE]._as_date(lot.expiration_date)),
            "stores": format_list(self.env, stores.mapped("display_name")),
            "quantity": item.uom_id.round(sum(quant.quantity for quant in quants)),
            "unit": item.uom_id.name,
        }
        if kind == EXPIRED:
            event = EVENT_STOCK_EXPIRED
            body = self.env._(
                "Lot %(lot)s of %(item)s expired on %(date)s. %(stores)s hold %(quantity)s %(unit)s to dispose of.",
                **values,
            )
        else:
            event = EVENT_STOCK_EXPIRING
            body = self.env._(
                "Lot %(lot)s of %(item)s expires on %(date)s. %(stores)s hold %(quantity)s %(unit)s.", **values
            )
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            event, lot, f"stock.{kind}:lot:{lot.id}", body, partners=stores._manager_partners()
        )

    def _settle_disposed(self):
        """An expired lot with nothing left in the laboratory's locations is disposed of."""
        expired = self.sudo().filtered(lambda lot: lot.status == LOT_EXPIRED or lot._is_expired())
        held = expired._held_quants().lot_id
        (expired - held).status = LOT_DISPOSED
        held.filtered(lambda lot: lot.status == LOT_AVAILABLE).status = LOT_EXPIRED

    def action_open_containers(self):
        return self.sudo().quant_ids.package_id.with_env(self.env)._action_open()

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        result = super().get_view(view_id, view_type, **options)
        # Every internal user reads lots, but only some read the orders and transfers Odoo counts on them; counting
        # documents the user cannot read fails, so their buttons are left out.
        hidden = {
            method
            for method, model in DOCUMENT_BUTTONS.items()
            if model in self.env and not self.env[model].has_access("read")
        }
        if view_type == "form" and hidden:
            root = etree.fromstring(result["arch"])
            for button in [button for button in root.iter("button") if button.get("name") in hidden]:
                parent = button.getparent()
                if parent is not None:
                    parent.remove(button)
            result["arch"] = etree.tostring(root, encoding="unicode")
        return result
