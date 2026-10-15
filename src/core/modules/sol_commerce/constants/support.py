"""Statuses of a support request, its task, and the bounds and context of an order's feedback."""

SUPPORT_OPEN = "open"
SUPPORT_ANSWERED = "answered"
SUPPORT_CLOSED = "closed"

SUPPORT_TRIGGER = "support_request_opened"
SUPPORT_ACTION = "answer"

FEEDBACK_MIN = 1
FEEDBACK_MAX = 5
# Set by the order page's feedback action, the only way an order is rated; Odoo's rating links are refused.
FEEDBACK_CONTEXT = "medilab_order_feedback"
