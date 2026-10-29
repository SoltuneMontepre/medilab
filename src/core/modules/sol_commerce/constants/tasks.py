"""Triggers and actions of the tasks that follow an order to its quotation and an invoice to its posting."""

QUOTATION_TRIGGER = "order_submitted"
QUOTATION_ACTION = "quote"
POSTING_TRIGGER = "invoice_drafted"
POSTING_ACTION = "post"
# Set while the system drafts an invoice it posts right away, so no posting task is created for it.
AUTO_POST_CONTEXT = "medilab_auto_post"
