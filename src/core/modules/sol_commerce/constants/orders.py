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

FOLLOW_UP_UNPAID = "unpaid"
FOLLOW_UP_PAID = "paid"
FOLLOW_UP_BY_QUOTATION_STATUS = {
    QUOTATION_SENT: FOLLOW_UP_UNPAID,
    QUOTATION_ACCEPTED: FOLLOW_UP_PAID,
    QUOTATION_DECLINED: QUOTATION_DECLINED,
    QUOTATION_EXPIRED: QUOTATION_EXPIRED,
}

PORTAL_LOCKED_ORDER_FIELDS = frozenset(
    {
        "advance_method",
        "advance_mode",
        "advance_value",
        "approval_status",
        "claimed_at",
        "customer_id",
        "expected_result_date",
        "order_status",
        "payment_deadline",
        "reordered_from_id",
        "reorder_note",
        "source",
        "submitted_at",
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
