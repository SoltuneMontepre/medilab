"""Statuses of a support request, its task, its messages and Medilab Mobile's lists of it, and the bounds and context of
an order's feedback."""

SUPPORT_OPEN = "open"
SUPPORT_ANSWERED = "answered"
SUPPORT_CLOSED = "closed"

SUPPORT_TRIGGER = "support_request_opened"
SUPPORT_ACTION = "answer"

COMMENT = "comment"
# Messages people write: on the portal or in the back office, and by e-mail reply.
WRITTEN_TYPES = (COMMENT, "email")

# Medilab Mobile's lists: the requests the person handles, and those waiting for a salesperson to take them.
SUPPORT_MINE = "mine"
SUPPORT_WAITING = "waiting"

FEEDBACK_MIN = 1
FEEDBACK_MAX = 5
# Set by the order page's feedback action, the only way an order is rated; Odoo's rating links are refused.
FEEDBACK_CONTEXT = "medilab_order_feedback"
