import hashlib
import hmac
import logging
import os

import requests

_logger = logging.getLogger(__name__)

PAYOS_BASE_URL = "https://api-merchant.payos.vn"
CLIENT_ID = "PAYOS_CLIENT_ID"
API_KEY = "PAYOS_API_KEY"
CHECKSUM_KEY = "PAYOS_CHECKSUM_KEY"
SUCCESS_CODE = "00"


class PayosClient:
    """Calls PayOS. The checksum key never leaves the signature, and the log line has no secrets."""

    def __init__(self, client_id, api_key, checksum_key):
        self.client_id = client_id
        self.api_key = api_key
        self.checksum_key = checksum_key

    def signature(self, data):
        # PayOS signs the fields in alphabetical order, joined as key=value.
        raw = "&".join(f"{key}={data[key]}" for key in sorted(data) if key != "signature" and data[key] is not None)
        return hmac.new(self.checksum_key.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def matches(self, data, signature):
        if not isinstance(data, dict) or not signature:
            return False
        return hmac.compare_digest(self.signature(data), signature)

    def payment_request_signature(self, amount, cancel_url, description, order_code, return_url):
        # The payment request signs these five fields in this order, not the alphabetical form.
        raw = (
            f"amount={amount}&cancelUrl={cancel_url}&description={description}"
            f"&orderCode={order_code}&returnUrl={return_url}"
        )
        return hmac.new(self.checksum_key.encode(), raw.encode(), hashlib.sha256).hexdigest()

    def request(self, method, path, payload=None):
        # One network call, so tests replace this method. The line names the call, never the keys.
        order_code = (payload or {}).get("orderCode")
        if order_code is None and path.rsplit("/", 1)[-1].isdigit():
            order_code = path.rsplit("/", 1)[-1]
        _logger.info("PayOS %s %s order %s", method, path, order_code)
        response = requests.request(
            method,
            f"{PAYOS_BASE_URL}{path}",
            json=payload,
            headers={"x-client-id": self.client_id, "x-api-key": self.api_key},
            timeout=30,
        )
        # HTTP 404 is the SDK's not-found result. Any other error still raises.
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        code = body.get("code") if isinstance(body, dict) else None
        if code not in (None, SUCCESS_CODE):
            raise requests.HTTPError(f"PayOS {method} {path} returned code {code}")
        return body


def payos_client_from_env():
    """A client when all three secrets are set; otherwise nothing, and PayOS is not called."""
    client_id = os.environ.get(CLIENT_ID)
    api_key = os.environ.get(API_KEY)
    checksum_key = os.environ.get(CHECKSUM_KEY)
    if not client_id or not api_key or not checksum_key:
        return None
    return PayosClient(client_id, api_key, checksum_key)
