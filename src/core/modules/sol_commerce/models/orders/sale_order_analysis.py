from odoo import api, fields, models
from odoo.tools import SQL

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    FOLLOW_UP_PAID,
    FOLLOW_UP_UNPAID,
    QUOTATION_ACCEPTED,
    QUOTATION_EXPIRED,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_CONFIRMED,
    STATUS_SUBMITTED,
)

SECONDS_PER_DAY = 86400
PIPELINE_STAGES = [
    ("unclaimed", "Unclaimed"),
    ("draft", "Draft"),
    ("sent", "Sent and unpaid"),
    ("accepted", "Accepted"),
    ("confirmed", "Confirmed"),
]
# The stage of a claimed order whose quotation is out, by where the quotation stands; a declined one leaves the pipeline.
CLAIMED_STAGES = {FOLLOW_UP_UNPAID: "sent", QUOTATION_EXPIRED: "sent", FOLLOW_UP_PAID: "accepted"}
# The steps each duration runs between.
DURATION_STEPS = {
    "days_to_quote": ("claimed_at", "quoted_at"),
    "days_to_payment": ("quoted_at", "accepted_at"),
    "days_to_confirmation": ("accepted_at", "confirmed_at"),
}


def _sql_days(name):
    """The SQL of a duration. It is empty until the order reaches the step, so averages leave out the orders before it."""
    start, end = DURATION_STEPS[name]
    return lambda _model, table: SQL(
        "EXTRACT(EPOCH FROM %s - %s)::float / %s", table[end], table[start], SECONDS_PER_DAY
    )


# Đơn Hàng: where the order stands in the sales pipeline, and what it counts for its salesperson's performance.
class SaleOrderAnalysis(models.Model):
    _inherit = MODEL_SALE_ORDER

    # unclaimed, draft, sent, accepted or confirmed; empty for a cart and for declined, completed and cancelled orders.
    pipeline_stage = fields.Selection(
        PIPELINE_STAGES, compute="_compute_pipeline_stage", store=True, index="btree_not_null"
    )
    # When the first quotation of the order was sent.
    quoted_at = fields.Datetime(compute="_compute_quoted_at", store=True)
    # When the customer accepted the quotation, by paying the advance or accepting one sent without.
    accepted_at = fields.Datetime(readonly=True, copy=False)
    # When sales confirmed the order; empty until it is confirmed.
    confirmed_at = fields.Datetime(readonly=True, copy=False)
    # Days from the claim to the first quotation.
    days_to_quote = fields.Float(
        "Days to Quote",
        compute="_compute_durations",
        compute_sql=_sql_days("days_to_quote"),
        compute_sudo=False,
        aggregator="avg",
    )
    # Days from the first quotation to the customer's acceptance.
    days_to_payment = fields.Float(
        "Days to Payment",
        compute="_compute_durations",
        compute_sql=_sql_days("days_to_payment"),
        compute_sudo=False,
        aggregator="avg",
    )
    # Days from the customer's acceptance to the confirmation.
    days_to_confirmation = fields.Float(
        "Days to Confirmation",
        compute="_compute_durations",
        compute_sql=_sql_days("days_to_confirmation"),
        compute_sudo=False,
        aggregator="avg",
    )
    # Quotations sent for the order, revisions included.
    quotation_sent_count = fields.Integer("Quotations Sent", compute="_compute_quotation_counts", store=True)
    # Quotations the customer accepted.
    quotation_accepted_count = fields.Integer("Quotations Accepted", compute="_compute_quotation_counts", store=True)
    # Quotations the customer declined, including those a revision replaced since.
    quotation_declined_count = fields.Integer("Quotations Declined", compute="_compute_quotation_counts", store=True)
    # Total excluding VAT once the order is confirmed; 0 before and once it is cancelled.
    revenue = fields.Monetary(compute="_compute_revenue", store=True)

    @api.depends("order_status", "state", "quotation_follow_up")
    def _compute_pipeline_stage(self):
        for order in self:
            order.pipeline_stage = order._pipeline_stage()

    def _pipeline_stage(self):
        self.ensure_one()
        if self.order_status == STATUS_SUBMITTED:
            return "unclaimed"
        if self.order_status == STATUS_CLAIMED:
            # A claimed order is draft until its quotation is sent, and again while sales revises it.
            return "draft" if self.state == "draft" else CLAIMED_STAGES.get(self.quotation_follow_up, False)
        if self.order_status == STATUS_CONFIRMED:
            return "confirmed"
        return False

    @api.depends("quotation_ids.sent_at")
    def _compute_quoted_at(self):
        for order in self:
            order.quoted_at = min(order.quotation_ids.mapped("sent_at"), default=False)

    @api.depends("claimed_at", "quoted_at", "accepted_at", "confirmed_at")
    def _compute_durations(self):
        for order in self:
            for name, (start, end) in DURATION_STEPS.items():
                begin, finish = order[start], order[end]
                order[name] = (finish - begin).total_seconds() / SECONDS_PER_DAY if begin and finish else 0.0

    @api.depends("quotation_ids.status", "quotation_ids.decline_reason")
    def _compute_quotation_counts(self):
        for order in self:
            quotations = order.quotation_ids
            order.quotation_sent_count = len(quotations)
            order.quotation_accepted_count = len(
                quotations.filtered(lambda quotation: quotation.status == QUOTATION_ACCEPTED)
            )
            order.quotation_declined_count = len(quotations.filtered("decline_reason"))

    @api.depends("order_status", "amount_untaxed")
    def _compute_revenue(self):
        for order in self:
            confirmed = order.order_status in (STATUS_CONFIRMED, STATUS_COMPLETED)
            order.revenue = order.amount_untaxed if confirmed else 0.0
