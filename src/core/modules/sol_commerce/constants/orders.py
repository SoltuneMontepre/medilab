"""Statuses of a sale order and of a cancellation request."""

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

PORTAL_LOCKED_ORDER_FIELDS = frozenset(
    {
        "approval_status",
        "claimed_at",
        "customer_id",
        "expected_result_date",
        "order_status",
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
