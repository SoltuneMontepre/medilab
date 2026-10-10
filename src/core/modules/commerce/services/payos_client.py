"""HTTP client of the PayOS merchant API; credentials are read from the environment at call time and never logged."""

import hashlib
import hmac
import json
import logging
import os

import requests

from odoo.addons.commerce.constants.payos import (
    BASE_URL,
    ENV_API_KEY,
    ENV_CHECKSUM_KEY,
    ENV_CLIENT_ID,
    SUCCESS_CODE,
    TIMEOUT_SECONDS,
)

_logger = logging.getLogger(__name__)

CREATE_SIGNATURE_FIELDS = ("amount", "cancelUrl", "description", "orderCode", "returnUrl")


class PayosError(Exception):
    """PayOS answered with an error code, or the answer could not be trusted."""

    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class PayosUnavailable(PayosError):
    """PayOS could not be reached or answered with a server error; the call is worth retrying."""


def _sorted(value):
    if isinstance(value, dict):
        return {key: _sorted(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted(item) for item in value]
    return value


def _signature_value(value):
    # The rules of PayOS's own SDK: empty for nothing, lower-case booleans, nested data as compact sorted JSON.
    if value is None or (isinstance(value, str) and value in ("null", "undefined")):
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(_sorted(value), separators=(",", ":"), ensure_ascii=False)
    return str(value)


def sign(data, key):
    """HMAC-SHA256 of the data as a query string with sorted keys, as PayOS signs its payloads."""
    message = "&".join(f"{name}={_signature_value(data[name])}" for name in sorted(data))
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify(data, signature, key):
    # Without a key nothing verifies, so an unconfigured server accepts no notification.
    return bool(key) and bool(signature) and hmac.compare_digest(sign(data, key), str(signature))


class PayosClient:
    def __init__(self, environ=None):
        self._environ = environ if environ is not None else os.environ

    def _credential(self, name):
        return self._environ.get(name, "")

    def is_configured(self):
        return all(self._credential(name) for name in (ENV_CLIENT_ID, ENV_API_KEY, ENV_CHECKSUM_KEY))

    def _checksum_key(self):
        return self._credential(ENV_CHECKSUM_KEY)

    def create_payment_link(self, order_code, amount, description, return_url, cancel_url, expired_at):
        body = {
            "orderCode": order_code,
            "amount": amount,
            "description": description,
            "returnUrl": return_url,
            "cancelUrl": cancel_url,
            "expiredAt": expired_at,
        }
        body["signature"] = sign({name: body[name] for name in CREATE_SIGNATURE_FIELDS}, self._checksum_key())
        return self._call("POST", "/v2/payment-requests", body, order_code)

    def get_payment_link(self, order_code):
        return self._call("GET", f"/v2/payment-requests/{order_code}", None, order_code)

    def cancel_payment_link(self, order_code, reason=None):
        body = {"cancellationReason": reason} if reason else {}
        return self._call("POST", f"/v2/payment-requests/{order_code}/cancel", body, order_code)

    def confirm_webhook(self, webhook_url):
        return self._call("POST", "/confirm-webhook", {"webhookUrl": webhook_url}, None, signed=False)

    def verify_webhook(self, payload):
        """The data of a webhook notification when its signature is right, else None."""
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not verify(data, payload.get("signature"), self._checksum_key()):
            return None
        return data

    def _call(self, method, path, body, order_code, signed=True):
        _logger.info("PayOS %s %s order %s", method, path, order_code)
        answer = self._request(method, path, body)
        code = answer.get("code")
        if code != SUCCESS_CODE:
            raise PayosError(answer.get("desc") or f"PayOS answered with code {code}", code=code)
        data = answer.get("data")
        if signed and not verify(data or {}, answer.get("signature"), self._checksum_key()):
            raise PayosError("The PayOS answer carries a wrong signature")
        return data

    def _request(self, method, path, body):
        # The one place the network is touched; tests replace it.
        headers = {"x-client-id": self._credential(ENV_CLIENT_ID), "x-api-key": self._credential(ENV_API_KEY)}
        try:
            response = requests.request(method, BASE_URL + path, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as error:
            raise PayosUnavailable(f"PayOS could not be reached: {type(error).__name__}") from error
        if response.status_code >= 500:
            raise PayosUnavailable(f"PayOS answered with HTTP {response.status_code}", status=response.status_code)
        try:
            return response.json()
        except ValueError as error:
            raise PayosError(
                f"PayOS answered with HTTP {response.status_code} and no JSON", status=response.status_code
            ) from error
