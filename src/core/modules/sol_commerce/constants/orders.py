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
FINISHED_STATUSES = (STATUS_COMPLETED, STATUS_CANCELLED)
NOTIFIED_STATUSES = (STATUS_SUBMITTED, STATUS_CLAIMED, STATUS_CANCELLED)

APPROVAL_NONE = "none"
APPROVAL_APPROVED = "approved"

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

# The line fields that stop changing once the order has a standing signature.
APPROVAL_FROZEN_LINE_FIELDS = frozenset(
    {"product_id", "product_uom_qty", "price_unit", "discount", "tax_ids", "sample_id"}
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
        "approval_status",
        "approved_at",
        "claimed_at",
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
