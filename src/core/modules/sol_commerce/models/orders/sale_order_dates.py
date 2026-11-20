from datetime import datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import DATE_FIELDS
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderDatesBase
else:
    SaleOrderDatesBase = object


# Đơn Hàng: the customer's requested date, the standard turnaround, the committed return date and priority requests.
class SaleOrderDates(models.Model, SaleOrderDatesBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Requested date: the date the customer wants the results.
        requested_date = fields.Date()
        # The customer's request for priority, and Sales's decision on it after the feasibility check.
        priority_request = fields.Selection(
            [("requested", "Requested"), ("accepted", "Accepted"), ("declined", "Declined")], copy=False
        )
        # True for an accepted priority request, which makes the test request's tests urgent.
        priority = fields.Boolean(string="Priority Order", compute="_compute_priority", store=True)
        # Working days results take from sample receipt: the longest standard turnaround of the order's ways of
        # testing, kept as it was when the quotation was sent.
        turnaround_days = fields.Integer(
            string="Turnaround (working days)", compute="_compute_turnaround_days", store=True, readonly=False
        )
        # The ways of testing of the order that have no standard turnaround yet, which keep the quotation from being sent.
        turnaround_missing = fields.Char(string="Missing Turnaround", compute="_compute_turnaround_missing")
        # The date results would be returned if the samples were received today.
        estimated_result_date = fields.Date(string="Estimated Return Date", compute="_compute_estimated_result_date")

    def write(self, vals):
        # A change recorded with the customer's agreement moves the committed return date of a confirmed order.
        changing = self.env.context.get(CHANGING_COMMITTED_DATE) and set(vals) == {"committed_date"}
        if DATE_FIELDS & set(vals) and not changing and self._frozen_by_quotation():
            raise UserError(self.env._("The dates cannot change after the quotation is sent. Revise the quotation."))
        return super().write(vals)

    @api.depends("priority_request")
    def _compute_priority(self):
        for order in self:
            order.priority = order.priority_request == "accepted"

    @api.depends("order_line.parameter_method_id")
    def _compute_turnaround_days(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            turnaround = requests._turnaround(order._ways())
            # A sent quotation keeps the turnaround it was sent with.
            frozen = order in order._frozen_by_quotation()
            order.turnaround_days = order.turnaround_days if frozen else turnaround["days"]

    @api.depends("order_line.parameter_method_id")
    def _compute_turnaround_missing(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            missing = requests._turnaround(order._ways())["missing"]
            order.turnaround_missing = ", ".join(missing.mapped("display_name")) or False

    @api.depends("turnaround_days")
    def _compute_estimated_result_date(self):
        requests = self.env[MODEL_TEST_REQUEST]
        zone = ZoneInfo(self.env.company.tz or "UTC")
        today = fields.Datetime.now().replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date()
        for order in self:
            order.estimated_result_date = (
                requests._date_after_working_days(today, order.turnaround_days) if order.turnaround_days else False
            )

    def _set_portal_dates(self, requested_date, priority):
        """Keep the date the customer wants the results and whether they ask for priority, from the cart."""
        self.ensure_one()
        try:
            requested = fields.Date.to_date(requested_date) if requested_date else False
        except ValueError as error:
            raise UserError(self.env._("Enter the date you want the results as a date.")) from error
        if priority and not requested:
            raise UserError(self.env._("Give the date you want the results to ask for priority."))
        self.sudo().write({"requested_date": requested, "priority_request": "requested" if priority else False})

    def _ways(self):
        # The ways of testing the order's parameters are tested by, a package's parameters included.
        self.ensure_one()
        return self.order_line._way_lines().parameter_method_id

    def action_accept_priority(self):
        """Accept the customer's priority request when the feasibility check says the requested date can be met; the
        requested date becomes the committed return date."""
        self.check_access("write")
        for order in self:
            if order.priority_request != "requested" or not order.requested_date:
                raise UserError(self.env._("Only a priority request with a requested date can be accepted."))
            check = self.env[MODEL_TEST_REQUEST]._check_priority(order._ways(), order.requested_date)
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
        return True

    def action_decline_priority(self):
        self.check_access("write")
        self.filtered(lambda order: order.priority_request == "requested").write({"priority_request": "declined"})
        return True

    def _check_quotation_can_be_sent(self):
        super()._check_quotation_can_be_sent()
        if self.turnaround_missing:
            raise UserError(
                self.env._(
                    "Set the standard turnaround of these ways of testing before sending the quotation: %s",
                    self.turnaround_missing,
                )
            )
        if self.priority_request == "requested":
            raise UserError(self.env._("Accept or decline the customer's priority request before sending."))
        deadline = self._priority_payment_deadline()
        if deadline and deadline <= fields.Datetime.now():
            raise UserError(
                self.env._(
                    "The advance would have to be paid before now for the results to be ready on %s. Agree a later "
                    "date with the customer.",
                    format_date(self.env, self.committed_date),
                )
            )
        estimate = self.estimated_result_date
        if not self.committed_date and self.requested_date and estimate and self.requested_date >= estimate:
            # A requested date the standard turnaround meets is the date Sales promises.
            self.committed_date = self.requested_date
        if self.committed_date and estimate and self.committed_date < estimate and not self.priority:
            raise UserError(
                self.env._(
                    "The committed return date is earlier than the standard turnaround allows, %s. Choose a later date "
                    "or accept a priority request.",
                    format_date(self.env, estimate),
                )
            )

    def _priority_payment_deadline(self):
        """The latest moment the advance of a priority order can be paid for the turnaround to meet its committed date:
        the end of the day the turnaround must start; False for any other order."""
        self.ensure_one()
        if not (self.priority and self.committed_date and self.turnaround_days):
            return False
        start = self.env[MODEL_TEST_REQUEST]._date_after_working_days(self.committed_date, -self.turnaround_days)
        zone = ZoneInfo(self.env.company.tz or "UTC")
        end_of_day = datetime.combine(start, time(23, 59, 59), tzinfo=zone)
        return end_of_day.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    def _latest_payment_deadline(self):
        return self._priority_payment_deadline() or super()._latest_payment_deadline()

    def action_change_committed_date(self):
        """Open the change of the confirmed order's committed return date, recorded with the customer's agreement."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_committed_date_change")
        action["context"] = {"default_request_id": self.test_request_id.id}
        return action
