from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import ADVANCE_NONE, DATE_FIELDS
from odoo.addons.sol_commerce.constants.settings import DEFAULT_PAYMENT_DEADLINE_DAYS, PAYMENT_DEADLINE_PARAMETER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_MACHINE_BOOKING,
    MODEL_PARAMETER_METHOD,
    MODEL_PERSON,
    MODEL_SAMPLE_TEST,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.models.sample_collection.committed_date_change import CHANGING_COMMITTED_DATE

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderDatesBase
else:
    SaleOrderDatesBase = object


# Đơn Hàng: the customer's requested date, the standard turnaround and the expected return date.
class SaleOrderDates(models.Model, SaleOrderDatesBase):
    _inherit = MODEL_SALE_ORDER

    if not TYPE_CHECKING:
        # Requested date: the date the customer wants the results.
        requested_date = fields.Date()
        # The day Sales agreed with the customer for the samples to be picked up, which return dates count from.
        expected_collection_date = fields.Date(string="Expected Sample Pickup", copy=False)
        # The date the results are expected back: the earliest the laboratory can return them from the expected pickup,
        # or the date an accepted priority request or a change agreed with the customer sets.
        committed_date = fields.Date(
            string="Expected Return Date",
            compute="_compute_committed_date",
            store=True,
            copy=False,
        )
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

    @api.depends(
        "order_line.parameter_method_id.turnaround_days",
        "product_line_ids.product_id",
        "product_line_ids.sample_type_id",
        "product_line_ids.parameter_method_id.turnaround_days",
    )
    def _compute_turnaround_days(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            turnaround = requests._turnaround(order._ways())
            # A sent quotation keeps the turnaround it was sent with.
            frozen = order in order._frozen_by_quotation()
            order.turnaround_days = order.turnaround_days if frozen else turnaround["days"]

    @api.depends(
        "order_line.parameter_method_id.turnaround_days",
        "product_line_ids.product_id",
        "product_line_ids.sample_type_id",
        "product_line_ids.parameter_method_id.turnaround_days",
    )
    def _compute_turnaround_missing(self):
        requests = self.env[MODEL_TEST_REQUEST]
        for order in self:
            missing = requests._turnaround(order._ways())["missing"]
            order.turnaround_missing = ", ".join(missing.mapped("display_name")) or False

    @api.depends(
        "turnaround_days",
        "order_line.parameter_method_id",
        "product_line_ids.product_id",
        "product_line_ids.sample_type_id",
        "product_line_ids.parameter_method_id",
        "expected_collection_date",
        "requested_date",
        "payment_deadline",
        "advance_method",
        "advance_mode",
        "priority_request",
    )
    def _compute_committed_date(self):
        for order in self:
            # A sent quotation, a confirmed order and an accepted priority request keep the date they have.
            keep = (
                order.priority_request == "accepted" or order.state != "draft" or order in order._frozen_by_quotation()
            )
            order.committed_date = order.committed_date if keep else order._earliest_return_date()

    def _collection_start(self, day):
        """The moment samples picked up on the day can be scheduled at the earliest: the end of that day in the
        company's time zone since no collection time is set yet, or now when none is given."""
        now = fields.Datetime.now()
        if not day:
            return now
        zone = ZoneInfo(self.env.company.tz or "UTC")
        start = datetime.combine(day, time(23, 59, 59), tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return max(start, now)

    def _estimation_lines(self):
        """Lines whose ways of testing feed turnaround and schedule simulation, following unsaved form edits."""
        self.ensure_one()
        if self._origin:
            return self.product_line_ids
        return self.product_line_ids or self.order_line

    def _ways(self):
        # The ways of testing the order's parameters are tested by, a package's parameters included.
        self.ensure_one()
        return self.env[MODEL_PARAMETER_METHOD].concat(self._estimation_lines()._resolved_ways())

    def _test_ways(self):
        """The way of each test the order brings the laboratory: one for each parameter line, a package's included."""
        self.ensure_one()
        return self._estimation_lines()._resolved_ways()

    @api.model
    def _days_off(self, first, last):
        """The days from first to last, both included, without working time in the company's working calendar."""
        zone = ZoneInfo(self.env.company.tz or "UTC")
        start, end = (
            datetime.combine(day, time.min, tzinfo=zone).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            for day in (first, last + timedelta(days=1))
        )
        # Without a person, the scheduler gives the company calendar's working time.
        intervals = self.env[MODEL_MACHINE_BOOKING].sudo()._working_time(self.env[MODEL_PERSON], start, end)
        working = {
            begin.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone).date() for begin, _finish in intervals
        }
        days = (first + timedelta(days=offset) for offset in range((last - first).days + 1))
        return [day for day in days if day not in working]

    @api.onchange("expected_collection_date")
    def _onchange_pickup_on_working_day(self):
        """Warn Sales of a pickup day the laboratory does not work; the collection then starts the next working day."""
        day = self.expected_collection_date
        if day and self._days_off(day, day):
            return {
                "warning": {
                    "title": self.env._("Company day off"),
                    "message": self.env._(
                        "%s is a company day off. The sample collection starts at the next working time.",
                        format_date(self.env, day),
                    ),
                }
            }
        return None

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
        start = self._estimate_start()
        requests = self.env[MODEL_TEST_REQUEST]
        estimate = requests._earliest_return(self._test_ways(), start, self.turnaround_days)
        return {**estimate, "start": self.env[MODEL_SAMPLE_TEST]._local_day(start)}

    def _estimate_start(self):
        """The moment the return estimate counts from: the expected sample pickup; without one, the advance's payment
        deadline when one is requested, otherwise now."""
        self.ensure_one()
        now = fields.Datetime.now()
        if self.expected_collection_date:
            return self._collection_start(self.expected_collection_date)
        if self.advance_method and self.advance_method != ADVANCE_NONE:
            deadline = self.payment_deadline
            if not deadline or deadline <= now:
                days = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_int(PAYMENT_DEADLINE_PARAMETER, DEFAULT_PAYMENT_DEADLINE_DAYS)
                )
                deadline = now + timedelta(days=days)
            return deadline
        return now

    def _estimate_start_day(self):
        """The day in the laboratory's time zone the return estimate counts from."""
        return self.env[MODEL_SAMPLE_TEST]._local_day(self._estimate_start())

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
