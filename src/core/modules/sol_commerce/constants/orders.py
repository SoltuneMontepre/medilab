"""Statuses of a sale order, of a cancellation request and of a quotation."""

SOURCE_PORTAL = "portal"
SOURCE_SALES = "sales"

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_CLAIMED = "claimed"
STATUS_CONFIRMED = "confirmed"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

CUSTOMER_CANCELLABLE = (STATUS_DRAFT, STATUS_SUBMITTED, STATUS_CLAIMED)
PORTAL_ORDERS_PER_PAGE = 20
# The latest orders the account page lists before linking to the order history.
ACCOUNT_RECENT_ORDERS = 5
# How many catalog items an order history row names before it counts the rest.
PORTAL_SUMMARY_ITEMS = 3
FINISHED_STATUSES = (STATUS_COMPLETED, STATUS_CANCELLED)
NOTIFIED_STATUSES = (STATUS_SUBMITTED, STATUS_CLAIMED, STATUS_CANCELLED)
# The statuses from which the order's content changes only through a revised quotation the customer accepts.
FROZEN_STATUSES = (STATUS_CONFIRMED, STATUS_COMPLETED)

CANCELLATION_TRIGGER = "order_cancellation_requested"
CANCELLATION_ACTION = "decide"
REQUESTED = "requested"
ACCEPTED = "accepted"
DECLINED = "declined"
WITHDRAWN = "withdrawn"

QUOTATION_SENT = "sent"
QUOTATION_ACCEPTED = "accepted"
QUOTATION_DECLINED = "declined"
QUOTATION_EXPIRED = "expired"
QUOTATION_REPLACED = "replaced"

ADVANCE_NONE = "none"
ADVANCE_FULL = "full"
ADVANCE_PERCENTAGE = "percentage"
ADVANCE_FIXED = "fixed"
ADVANCE_PAID_STATES = ("paid", "in_payment")
ADVANCE_TOUCHED_STATES = (*ADVANCE_PAID_STATES, "partial")
# The advance fields stop changing once the current revision is sent.
ADVANCE_FIELDS = frozenset({"advance_method", "advance_mode", "advance_value"})
# The quotation statuses under which the order's advance, lines and samples stay as quoted.
QUOTATION_FROZEN_STATUSES = (QUOTATION_SENT, QUOTATION_ACCEPTED)

FOLLOW_UP_UNPAID = "unpaid"
FOLLOW_UP_PAID = "paid"
FOLLOW_UP_BY_QUOTATION_STATUS = {
    QUOTATION_SENT: FOLLOW_UP_UNPAID,
    QUOTATION_ACCEPTED: FOLLOW_UP_PAID,
    QUOTATION_DECLINED: QUOTATION_DECLINED,
    QUOTATION_EXPIRED: QUOTATION_EXPIRED,
}

# What the customer and sales agreed on the order itself, and the test request made from it: they stop changing once
# the order is confirmed.
FROZEN_ORDER_FIELDS = frozenset({"customer_id", "partner_id", "payment_deadline", "validity_date", "test_request_id"})
# The line fields that stop changing once the quotation is sent or the order is confirmed; a line that became a down
# payment or a package part would no longer count as content.
FROZEN_LINE_FIELDS = frozenset(
    {
        "product_id",
        "product_uom_qty",
        "price_unit",
        "discount",
        "tax_ids",
        "sample_id",
        "is_downpayment",
        "linked_line_id",
    }
)

# The sample fields that stop changing with the lines.
FROZEN_SAMPLE_FIELDS = frozenset(
    {"order_id", "customer_sample_name", "sample_type_id", "physical_state", "regulation_id", "sequence"}
)

PORTAL_LOCKED_ORDER_FIELDS = frozenset(
    {
        "accepted_at",
        "advance_method",
        "advance_mode",
        "advance_value",
        "claimed_at",
        "confirmed_at",
        "customer_id",
        "expected_result_date",
        "order_status",
        "payment_deadline",
        "reordered_from_id",
        "reorder_note",
        "source",
        "submitted_at",
        "test_request_id",
        "user_id",
    }
)
PORTAL_LOCKED_LINE_FIELDS = frozenset(
    {
        "discount",
        "price_subtotal",
        "price_tax",
        "price_total",
        "price_unit",
        "purchase_price",
        "tax_ids",
        "technical_price_unit",
    }
)
