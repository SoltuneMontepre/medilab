from datetime import timedelta
from typing import TYPE_CHECKING

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    COLLECTION_DAYS,
    COLLECTION_DROP_OFF,
    COLLECTION_METHODS,
    COLLECTION_PICKUP,
    COLLECTION_TIMES,
    STATUS_DRAFT,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderCollectionBase
else:
    SaleOrderCollectionBase = object


# Đơn Hàng: how the customer wants the samples to reach the laboratory, given when ordering on the portal.
class SaleOrderCollection(models.Model, SaleOrderCollectionBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Whether the laboratory picks the samples up or the customer brings them.
        collection_method = fields.Selection(COLLECTION_METHODS, string="Sample Collection", copy=False)
        # Where the customer wants the samples picked up.
        collection_address = fields.Text(string="Pickup Address", copy=False)
        # The part of the day the customer prefers for the pickup or the drop-off.
        collection_time = fields.Selection(COLLECTION_TIMES, string="Preferred Time", copy=False)
        # What the customer tells collection staff, such as whom to call at the gate.
        collection_note = fields.Text(string="Collection Note", copy=False)

    def _collection_days(self):
        """The working days the customer can choose for the pickup or the drop-off: from tomorrow to a month ahead."""
        self.ensure_one()
        first = fields.Date.context_today(self) + timedelta(days=1)
        last = first + timedelta(days=COLLECTION_DAYS - 1)
        days_off = set(self._days_off(first, last))
        days = (first + timedelta(days=offset) for offset in range(COLLECTION_DAYS))
        return [day for day in days if day not in days_off]

    def _prefill_collection(self):
        """Start a portal order's collection with what the customer chose on their last order, or else the pickup at
        the customer's address."""
        self.ensure_one()
        order = self.sudo()
        if order.collection_method:
            return
        previous = order.browse()
        if order.customer_id:
            previous = order.search(
                Domain("customer_id", "=", order.customer_id.id)
                & Domain("id", "!=", order.id)
                & Domain("collection_method", "!=", False)
                & Domain("order_status", "!=", STATUS_DRAFT),
                order="id desc",
                limit=1,
            )
        order.write(
            {
                "collection_method": previous.collection_method or COLLECTION_PICKUP,
                "collection_address": previous.collection_address
                or (order.customer_id and order.customer_id._display_address(without_name=True))
                or False,
                "collection_time": previous.collection_time or "any",
                "collection_note": previous.collection_note or False,
            }
        )

    def _save_portal_collection(self, values):
        """Keep the collection details the customer is giving, ignoring what cannot be kept yet."""
        self.ensure_one()
        vals = {}
        if values.get("collection_method") in dict(COLLECTION_METHODS):
            vals["collection_method"] = values["collection_method"]
        if "collection_address" in values:
            vals["collection_address"] = (values["collection_address"] or "").strip() or False
        if values.get("collection_time") in dict(COLLECTION_TIMES):
            vals["collection_time"] = values["collection_time"]
        if "collection_note" in values:
            vals["collection_note"] = (values["collection_note"] or "").strip() or False
        if "collection_date" in values:
            day = values["collection_date"]
            chosen = fields.Date.to_date(day) if day and day.count("-") == 2 else False
            if not chosen or chosen in self._collection_days():
                vals["expected_collection_date"] = chosen
        if vals:
            self.sudo().write(vals)

    def _check_portal_collection(self):
        """Refuse to submit a portal order whose collection is incomplete or whose day cannot be chosen."""
        self.ensure_one()
        order = self.sudo()
        _ = self.env._
        if not order.collection_method:
            raise UserError(_("Choose how the samples reach the laboratory."))
        if order.collection_method == COLLECTION_PICKUP and not order.collection_address:
            raise UserError(_("Give the address the samples are picked up from."))
        day = order.expected_collection_date
        if day and day not in order._collection_days():
            raise UserError(_("Choose a working day within the next month for the samples."))
        order._check_requested_date(order.requested_date)

    def _collection_preference_lines(self, env):
        """The customer's wishes for the collection, in the language of the environment, for collection staff."""
        self.ensure_one()
        order = self.sudo()
        lines = []
        if order.collection_method == COLLECTION_DROP_OFF:
            lines.append(env._("The customer brings the samples to the laboratory."))
        if order.collection_time and order.collection_time != "any":
            times = dict(order._fields["collection_time"]._description_selection(env))
            lines.append(env._("Preferred time: %s", times[order.collection_time]))
        if order.collection_note:
            lines.append(env._("Customer note: %s", order.collection_note))
        return lines
