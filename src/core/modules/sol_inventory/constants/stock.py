"""Statuses of lots and containers, and the Odoo operation and order states the module relies on."""

LOT_AVAILABLE = "available"
LOT_EXPIRED = "expired"
LOT_DISPOSED = "disposed"

CONTAINER_SEALED = "sealed"
CONTAINER_OPENED = "opened"
CONTAINER_DEPLETED = "depleted"
CONTAINER_DISPOSED = "disposed"
CONTAINER_MISSING = "missing"

# Odoo's operation type code of a receipt.
RECEIPT_CODE = "incoming"
# Odoo's states of a purchase order: draft while it is prepared and signed, purchase once sent to the supplier.
ORDER_DRAFT = "draft"
ORDER_SENT = "purchase"
# Odoo's receipt status of an order whose receipts brought everything in.
RECEIVED = "full"
# Odoo's last states of orders, transfers and moves.
DONE = "done"
CANCELLED = "cancel"
