from datetime import date
from typing import TYPE_CHECKING, Literal

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools.misc import format_date, formatLang

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.settings import PRIORITY_ORDERS_ON
from odoo.addons.sol_commerce.constants.xml_ids import PRIORITY_SURCHARGE_PRODUCT
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.services.record_id import persisted_id, persisted_ids

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderPriorityBase
else:
    SaleOrderPriorityBase = object

# Set while the surcharge lines are brought in line, so writing them does not start it again.
SYNCING_PRIORITY = "medilab_syncing_priority"
# Order fields whose change can make an order a priority request or no longer one, or change its surcharge.
PRIORITY_FIELDS = frozenset({"order_line", "product_line_ids", "requested_date", "expected_collection_date"})


# Đơn Hàng: the priority request an early requested date makes, and the surcharge an accepted one adds.
class SaleOrderPriority(models.Model, SaleOrderPriorityBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # requested while the requested date is earlier than the standard return date, until Sales accepts or declines
        # it; empty for any other order.
        priority_request = fields.Selection(
            [("requested", "Requested"), ("accepted", "Accepted"), ("declined", "Declined")],
            compute="_compute_priority_request",
            store=True,
            readonly=False,
            copy=False,
            tracking=True,
        )
        # True for an accepted priority request, which makes the test request's tests urgent.
        priority = fields.Boolean(string="Priority Order", compute="_compute_priority", store=True)
        # The date the results come back by the standard turnaround, counted from the expected pickup.
        standard_return_date = fields.Date(compute="_compute_requested_window")
        # Earliest date the date picker allows for the requested date.
        min_requested_date = fields.Date(compute="_compute_requested_window")

    @api.model
    def _priority_settings(self):
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        return {
            "offered": settings._get_parameter("priority_orders") == PRIORITY_ORDERS_ON,
            "min_days": settings._get_parameter("priority_min_turnaround_days"),
            "surcharge": settings._get_parameter("priority_surcharge_percent"),
        }

    @api.depends("turnaround_days", "expected_collection_date", "payment_deadline", "advance_method")
    def _compute_requested_window(self):
        for order in self:
            order.standard_return_date = order._standard_return_date()
            order.min_requested_date = order._min_requested_date()

    @api.depends("requested_date", "turnaround_days", "expected_collection_date")
    def _compute_priority_request(self):
        frozen = self._frozen_by_quotation()
        for order in self:
            if order.state != "draft" or order in frozen:
                order.priority_request = order.priority_request
            elif order._is_priority_date():
                order.priority_request = order.priority_request or "requested"
            else:
                order.priority_request = False

    @api.depends("priority_request")
    def _compute_priority(self):
        for order in self:
            order.priority = order.priority_request == "accepted"

    def _standard_return_date(self) -> date | Literal[False]:
        """The day results come back by the standard turnaround from the day the estimate starts; False without one."""
        self.ensure_one()
        if not self.turnaround_days:
            return False
        return self.env[MODEL_TEST_REQUEST]._date_after_working_days(self._estimate_start_day(), self.turnaround_days)

    def _min_requested_date(self) -> date:
        """The earliest requested date allowed: the shortest priority turnaround while priority orders are offered,
        never later than the standard return date, otherwise the standard return date."""
        self.ensure_one()
        settings = self._priority_settings()
        standard = self._standard_return_date()
        if standard and not settings["offered"]:
            return standard
        shortest = self.env[MODEL_TEST_REQUEST]._date_after_working_days(
            self._estimate_start_day(), settings["min_days"]
        )
        return min(shortest, standard) if standard else shortest

    def _is_priority_date(self):
        self.ensure_one()
        standard = self._standard_return_date()
        return bool(
            self.requested_date and standard and self.requested_date < standard and self._priority_settings()["offered"]
        )

    def _cart_priority_window(self, requested=None):
        """What the cart shows about the requested date: the earliest the customer may pick, the standard return date,
        whether the date given is a priority request, and the surcharge accepting it would add."""
        self.ensure_one()
        settings = self._priority_settings()
        standard = self._standard_return_date()
        try:
            requested = fields.Date.to_date(requested) if requested else self.requested_date
        except ValueError:
            requested = self.requested_date
        rate = settings["surcharge"] if settings["offered"] else 0
        surcharge = self.currency_id.round(self.catalog_total * rate / 100) if rate else 0
        if surcharge:
            notice = self.env._(
                "A date before the standard return date is a priority request, which adds %(amount)s excluding VAT "
                "(%(rate)s%%). Sales confirms whether the laboratory can meet it.",
                amount=formatLang(self.env, surcharge, currency_obj=self.currency_id),
                rate=f"{rate:g}",
            )
        else:
            notice = self.env._(
                "A date before the standard return date is a priority request. Sales confirms whether the laboratory "
                "can meet it."
            )
        return {
            "offered": settings["offered"],
            "earliest": self._min_requested_date(),
            "standard": standard,
            "standard_text": standard
            and self.env._(
                "Standard return date: %(date)s, %(days)s working days after the samples are picked up today.",
                date=format_date(self.env, standard),
                days=self.turnaround_days,
            ),
            "priority": bool(settings["offered"] and requested and standard and requested < standard),
            "surcharge": surcharge,
            "notice": notice,
        }

    def _check_requested_date(self, requested):
        """Refuse a requested date before the earliest the priority settings allow."""
        self.ensure_one()
        earliest = self._min_requested_date()
        if requested and requested < earliest:
            raise UserError(
                self.env._("Choose a date on or after %s for the results.", format_date(self.env, earliest))
            )

    def _set_portal_dates(self, requested_date):
        """Keep the date the customer wants the results, from the cart."""
        self.ensure_one()
        try:
            requested = fields.Date.to_date(requested_date) if requested_date else False
        except ValueError as error:
            raise UserError(self.env._("Enter the date you want the results as a date.")) from error
        self._check_requested_date(requested)
        self.sudo().write({"requested_date": requested})

    def write(self, vals):
        result = super().write(vals)
        if PRIORITY_FIELDS & set(vals):
            self._sync_priority()
        return result

    def action_accept_priority(self):
        """Accept the customer's priority request when the feasibility check says the requested date can be met; the
        requested date becomes the expected return date and the surcharge is added."""
        self.check_access("write")
        for order in self:
            if order.priority_request != "requested" or not order.requested_date:
                raise UserError(self.env._("Only a priority request with a requested date can be accepted."))
            check = self.env[MODEL_TEST_REQUEST]._check_priority(order._test_ways(), order.requested_date)
            if not check["feasible"]:
                if check["date"]:
                    raise UserError(
                        self.env._(
                            "The laboratory cannot return results by %(requested)s. The earliest feasible date is "
                            "%(earliest)s; offer it to the customer.",
                            requested=format_date(self.env, order.requested_date),
                            earliest=format_date(self.env, check["date"]),
                        )
                    )
                raise UserError(self.env._("The priority request cannot be checked: %s", " ".join(check["reasons"])))
            order.write({"priority_request": "accepted", "committed_date": order.requested_date})
        self._sync_priority()
        return True

    def action_decline_priority(self):
        self.check_access("write")
        self.filtered(lambda order: order.priority_request == "requested").write({"priority_request": "declined"})
        self._sync_priority()
        return True

    def _priority_surcharge_lines(self):
        product = self.env.ref(PRIORITY_SURCHARGE_PRODUCT)
        return self.order_line.filtered(lambda line: line.product_id == product)

    def _sync_priority(self):
        """Work the priority request of the orders whose quotation is not sent out again, and bring their surcharge
        lines in line with it: one line for each tax of the ordered lines while priority is accepted. The surcharge
        counts each ordered line after its own discount; a whole-quotation discount does not lower it."""
        if self.env.context.get(SYNCING_PRIORITY):
            return
        orders = self.sudo().with_context(**{SYNCING_PRIORITY: True}).exists()
        orders = orders.filtered(lambda order: order.state == "draft") - orders._frozen_by_quotation()
        if not orders:
            return
        # The priority settings are not a dependency Odoo follows, so the request is worked out again here.
        self.env.add_to_compute(orders._fields["priority_request"], orders)
        rate = self._priority_settings()["surcharge"]
        for order in orders:
            order._sync_priority_surcharge(rate if order.priority_request == "accepted" else 0)

    def _sync_priority_surcharge(self, rate):
        self.ensure_one()
        bases = {}
        if rate:
            for line in self._catalog_lines():
                bases[line.tax_ids] = bases.get(line.tax_ids, 0) + line.price_subtotal
        product = self.env.ref(PRIORITY_SURCHARGE_PRODUCT).with_context(lang=self.partner_id.lang)
        # In the customer's language, as the quotation they receive is.
        name = f"{product.name} ({rate:g}%)"
        stale = self._priority_surcharge_lines()
        commands = []
        for taxes, base in bases.items():
            price = self.currency_id.round(base * rate / 100)
            line = stale.filtered(lambda item, taxes=taxes: item.tax_ids == taxes)[:1]
            stale -= line
            if not line:
                commands.append(
                    Command.create(
                        {
                            "product_id": product.id,
                            "name": name,
                            "product_uom_qty": 1,
                            "price_unit": price,
                            "tax_ids": [Command.set(taxes.ids)],
                            "sequence": 10000,
                        }
                    )
                )
            elif line.price_unit != price or line.name != name or line.discount:
                commands.append(Command.update(persisted_id(line), {"price_unit": price, "name": name, "discount": 0}))
        commands.extend(Command.unlink(line_id) for line_id in persisted_ids(stale))
        if commands:
            self.write({"order_line": commands})
