from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import ADVANCE_NONE, DATE_FIELDS
from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TEST_REQUEST
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderDatesBase
else:
    SaleOrderDatesBase = object


# Đơn Hàng: the customer's requested date, the standard turnaround, the expected return date and priority requests.
class SaleOrderDates(models.Model, SaleOrderDatesBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Requested date: the date the customer wants the results.
        requested_date = fields.Date()
        # The day Sales agreed with the customer for the samples to be picked up, which return dates count from.
        expected_collection_date = fields.Date(string="Expected Sample Pickup", copy=False)
        # The date the results are expected back: the earliest the laboratory can return them from the expected pickup,
        # until Sales sets a later date or an accepted priority request sets it.
        committed_date = fields.Date(
            string="Expected Return Date",
            compute="_compute_committed_date",
            store=True,
            readonly=False,
            copy=False,
        )
        # Earliest date the date picker allows for Expected Return Date.
        min_committed_date = fields.Date(compute="_compute_min_committed_date")
        # The customer's request for priority, and Sales's decision on it after the feasibility check.
        priority_request = fields.Selection(
            [("requested", "Requested"), ("accepted", "Accepted"), ("declined", "Declined")], copy=False
        )
        # True for an accepted priority request, which makes the test request's tests urgent.
        priority = fields.Boolean(string="Priority Order", compute="_compute_priority", store=True)
        # Working days results take from sample receipt: the longest standard turnaround of the order's ways of
        # testing, kept as it was when the quotation was sent.
        turnaround_days = fields.Integer(
            string="Turnaround (working days)",
            compute="_compute_turnaround_days",
            store=True,
            readonly=False,
            help="Working days from sample receipt to results: the longest standard turnaround of the order's ways of "
            "testing, set on each way in the catalog.",
        )
        # The ways of testing of the order that have no standard turnaround yet, which keep the quotation from being sent.
        turnaround_missing = fields.Char(string="Missing Turnaround", compute="_compute_turnaround_missing")

    def write(self, vals):
        # A change recorded with the customer's agreement moves the expected return date of a confirmed order.
        changing = self.env.context.get(CHANGING_COMMITTED_DATE) and set(vals) == {"committed_date"}
        if DATE_FIELDS & set(vals) and not changing and self._frozen_by_quotation():
            raise UserError(self.env._("The dates cannot change after the quotation is sent. Revise the quotation."))
        return super().write(vals)

    @api.depends("priority_request")
    def _compute_priority(self):
        for order in self:
            order.priority = order.priority_request == "accepted"

    @api.depends("order_line.parameter_method_id.turnaround_days")
    def _compute_turnaround_days(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            turnaround = requests._turnaround(order._ways())
            # A sent quotation keeps the turnaround it was sent with.
            frozen = order in order._frozen_by_quotation()
            order.turnaround_days = order.turnaround_days if frozen else turnaround["days"]

    @api.depends("order_line.parameter_method_id.turnaround_days")
    def _compute_turnaround_missing(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            missing = requests._turnaround(order._ways())["missing"]
            order.turnaround_missing = ", ".join(missing.mapped("display_name")) or False

    @api.depends(
        "turnaround_days",
        "order_line.parameter_method_id",
        "expected_collection_date",
        "requested_date",
        "payment_deadline",
        "advance_method",
        "advance_mode",
    )
    def _compute_committed_date(self):
        for order in self:
            # A sent quotation, a confirmed order and an accepted priority request keep the date they have.
            keep = (
                order.priority_request == "accepted" or order.state != "draft" or order in order._frozen_by_quotation()
            )
            order.committed_date = order.committed_date if keep else order._earliest_return_date()

    @api.depends(
        "order_line.parameter_method_id",
        "expected_collection_date",
        "priority",
    )
    def _compute_min_committed_date(self):
        today = fields.Date.context_today(self)
        for order in self:
            if order.priority:
                order.min_committed_date = today
            else:
                order.min_committed_date = order._earliest_return_date() or order.expected_collection_date or today

    def _collection_start(self, day):
        """The moment samples picked up on the day can be scheduled at the earliest: the end of that day in the
        company's time zone since no collection time is set yet, or now when none is given."""
        now = fields.Datetime.now()
        if not day:
            return now
        zone = ZoneInfo(self.env.company.tz or "UTC")
        start = datetime.combine(day, time(23, 59, 59), tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return max(start, now)

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

    def _test_ways(self):
        """The way of each test the order brings the laboratory: one for each parameter line, a package's included."""
        self.ensure_one()
        return [line.parameter_method_id for line in self.order_line._way_lines() if line.parameter_method_id]

    def action_accept_priority(self):
        """Accept the customer's priority request when the feasibility check says the requested date can be met; the
        requested date becomes the expected return date."""
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
        if self.expected_collection_date and self.expected_collection_date < fields.Date.context_today(self):
            raise UserError(self.env._("Give an expected pickup day that has not passed."))
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
        estimate = self._earliest_return_date()
        if self.committed_date and estimate and self.committed_date < estimate and not self.priority:
            raise UserError(
                self.env._(
                    "The expected return date is earlier than the laboratory can return results, %s. Choose a later "
                    "date or accept a priority request.",
                    format_date(self.env, estimate),
                )
            )

    def _earliest_return_date(self) -> date | Literal[False]:
        """The earliest date the laboratory can return the results; False without a turnaround."""
        value = self._return_estimate()["date"]
        return value if isinstance(value, date) else False

    def _return_estimate(self):
        """How the earliest return date is reached: the turnaround, or the laboratory's held work when it leaves the
        order's tests to finish later, plus the safety margin, counted from the expected sample pickup. Without one it
        counts from the day the samples can be received at the latest without delaying the order, the advance's payment
        deadline when one is requested, otherwise today. The date is False without a turnaround."""
        self.ensure_one()
        if not self.turnaround_days:
            return {"date": False}
        now = fields.Datetime.now()
        start = now
        if self.expected_collection_date:
            start = self._collection_start(self.expected_collection_date)
        elif self.advance_method and self.advance_method != ADVANCE_NONE:
            deadline = self.payment_deadline
            if not deadline or deadline <= now:
                days = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_int(PAYMENT_DEADLINE_PARAMETER, DEFAULT_PAYMENT_DEADLINE_DAYS)
                )
                deadline = now + timedelta(days=days)
            start = deadline
        requests = self.env[MODEL_TEST_REQUEST]
        estimate = requests._earliest_return(self._test_ways(), start, self.turnaround_days)
        return {**estimate, "start": self.env[MODEL_SAMPLE_TEST]._local_day(start)}

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
        """Open the change of the confirmed order's expected return date, recorded with the customer's agreement."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id("sol_laboratory.action_medilab_committed_date_change")
        action["context"] = {"default_request_id": self.test_request_id.id}
        return action
