import re
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools.sql import escape_like_value

from odoo.addons.sol_inventory.constants.models import MODEL_PRODUCT, MODEL_STOCK_LOT, MODEL_STOCK_PACKAGE
from odoo.addons.sol_inventory.constants.stock import (
    CONTAINER_DEPLETED,
    CONTAINER_DISPOSED,
    CONTAINER_MISSING,
    CONTAINER_OPENED,
    CONTAINER_SEALED,
)
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_ACTION
from odoo.addons.sol_laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_stock_package as StockPackageBase
else:
    StockPackageBase = object


# Chai/Lọ
class StockPackage(models.Model, StockPackageBase):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_STOCK_PACKAGE
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_STOCK_PACKAGE, MODEL_ARCHIVE_MIXIN]

    if not TYPE_CHECKING:
        # sealed, opened, depleted, disposed or missing.
        status = fields.Selection(
            [
                (CONTAINER_SEALED, "Sealed"),
                (CONTAINER_OPENED, "Opened"),
                (CONTAINER_DEPLETED, "Depleted"),
                (CONTAINER_DISPOSED, "Disposed"),
                (CONTAINER_MISSING, "Missing"),
            ],
            required=True,
            default=CONTAINER_SEALED,
        )
        # Last day the container can be used: its lot's expiry date while it is sealed.
        usable_until = fields.Date(string="Usable Until", compute="_compute_usable_until", store=True)
        # The item in the container.
        item_id = fields.Many2one(MODEL_PRODUCT, string="Item", compute="_compute_content")
        # The lot of the stock in the container.
        lot_id = fields.Many2one(MODEL_STOCK_LOT, string="Lot", compute="_compute_content")
        # Quantity left in the container, in its item's unit.
        quantity = fields.Float(string="Quantity", digits="Product Unit", compute="_compute_content")

    _name_unique = models.Constraint("UNIQUE(name)", "Another container already has this code.")
    _location_status_idx = models.Index("(location_id, status)")
    _status_usable_idx = models.Index("(status, usable_until)")

    @api.depends("quant_ids.lot_id", "quant_ids.quantity")
    def _compute_content(self):
        for container in self:
            quants = container.sudo().quant_ids
            container.item_id = quants.product_id[:1]
            container.lot_id = quants.lot_id[:1]
            container.quantity = sum(quants.mapped("quantity"))

    @api.depends("quant_ids.lot_id.expiration_date")
    def _compute_usable_until(self):
        for container in self:
            expiry = container.sudo().quant_ids.lot_id[:1].expiration_date
            # The day in the laboratory's time zone, whoever triggers the recompute.
            laboratory = container.with_context(tz=self.env.company.tz or "UTC")
            container.usable_until = expiry and fields.Datetime.context_timestamp(laboratory, expiry).date()

    def _action_open(self):
        """The Containers screen, listing these containers."""
        action = self.env["ir.actions.actions"]._for_xml_id(CONTAINER_ACTION)
        action["domain"] = [("id", "in", self.ids)]
        return action

    @api.model
    def _next_container_codes(self, lot_name, count):
        """The next count codes of containers of a lot, such as Lot123-01, numbered on from the codes already used."""
        prefix = f"{lot_name}-"
        used = self.sudo().search_fetch(Domain("name", "=like", f"{escape_like_value(prefix)}%"), ["name"])
        pattern = re.compile(rf"{re.escape(prefix)}(\d+)")
        numbers = [
            int(match.group(1)) for match in (pattern.fullmatch(name or "") for name in used.mapped("name")) if match
        ]
        start = max(numbers, default=0) + 1
        return [f"{prefix}{number:02d}" for number in range(start, start + count)]
