"""PayOS integration: endpoints, environment variables, status mapping, jobs and limits."""

BASE_URL = "https://api-merchant.payos.vn"
# Credentials come from the environment, injected by Doppler; nothing is stored in the database.
ENV_CLIENT_ID = "PAYOS_CLIENT_ID"
ENV_API_KEY = "PAYOS_API_KEY"
ENV_CHECKSUM_KEY = "PAYOS_CHECKSUM_KEY"
TIMEOUT_SECONDS = 15
SUCCESS_CODE = "00"

# PayOS link statuses mapped to the local ones.
STATUS_MAP = {
    "PENDING": "pending",
    "PROCESSING": "pending",
    "UNDERPAID": "pending",
    "PAID": "paid",
    "CANCELLED": "cancelled",
    "EXPIRED": "expired",
    "FAILED": "failed",
}
# A status moves only forward in this order; PayOS's paid wins over a local cancelled or expired.
STATUS_ORDER = {"created": 0, "pending": 1, "cancelled": 2, "expired": 2, "failed": 2, "paid": 3}
FINAL_STATUSES = ("paid", "cancelled", "expired", "failed")

# The methods PayOS offers, each with its settings field; the portal offers only the enabled ones.
PAYMENT_METHODS = {"qr_transfer": "payos_method_qr_transfer"}

JOB_CALLS = "payos.calls"
JOB_POLL = "payos.poll"
# Minutes between two status checks of a pending link, and the margin after expiry before polling stops.
POLL_INTERVAL_MINUTES = 15
POLL_GRACE_MINUTES = 60

# PayOS limits the transfer description for bank accounts not linked through PayOS.
DESCRIPTION_MAX_LENGTH = 9
# PayOS reports transaction times without a timezone; they are read as Vietnam time.
PAYOS_TIMEZONE = "Asia/Ho_Chi_Minh"

WEBHOOK_ROUTE = "/medilab/payos/webhook"
RETURN_ROUTE = "/medilab/payos/return"
CANCEL_ROUTE = "/medilab/payos/cancel"
# Checkout page of a link PayOS already knows, when its answer does not carry the page itself.
CHECKOUT_URL_FORMAT = "https://pay.payos.vn/web/{}"
