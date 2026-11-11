"""Keep the callback capability and debug request headers out of Odoo's HTTP access/error records."""

import logging
import re
from urllib.parse import unquote

from odoo.http import request

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_LOGGER,
    CALLBACK_PREFIX,
    CALLBACK_REQUEST_EVIDENCE,
)

_logger = logging.getLogger(CALLBACK_LOGGER)
NETWORK_LOGGERS = ("urllib3", "requests", "botocore", "boto3", "s3transfer")
MAX_LOG_TEXT_LENGTH = 64 * 1024
MAX_LOG_URL_DECODE_PASSES = 2
PERCENT_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")


def _may_reference_callback(text):
    # Fail closed rather than truncate a hidden reference or keep decoding untrusted diagnostics.
    if len(text) > MAX_LOG_TEXT_LENGTH:
        return True
    for _depth in range(MAX_LOG_URL_DECODE_PASSES):
        if CALLBACK_PREFIX in text:
            return True
        decoded = unquote(text)
        if decoded == text:
            return False
        text = decoded
    return CALLBACK_PREFIX in text or PERCENT_ESCAPE.search(text) is not None


def _references_callback(record):
    # Watchdogs run outside the request context and put thread URLs in message arguments or exception chains.
    texts = [
        record.getMessage(),
        getattr(record, "http_request_line", ""),
        getattr(record, "colored_message", ""),
        record.exc_text or "",
        record.stack_info or "",
    ]
    if record.exc_info:
        texts.append(logging.Formatter().formatException(record.exc_info))
    return any(_may_reference_callback(text) for text in texts)


class EditingCallbackFilter(logging.Filter):
    def filter(self, record):
        name = record.name or ""
        transport = any(name == prefix or name.startswith(prefix + ".") for prefix in ("odoo.http", *NETWORK_LOGGERS))
        callback = (
            transport and request and request.httprequest.path.startswith(CALLBACK_PREFIX)
        ) or _references_callback(record)
        if not callback:
            return super().filter(record)
        # The server already expanded debug headers and its colored message; replace all representations together.
        record.msg = "ONLYOFFICE callback HTTP status=%s"
        record.args = (getattr(record, "http_response_status", "-"),)
        record.http_request_line = CALLBACK_PREFIX + "[redacted]"
        record.http_headers = ()
        record.colored_message = record.getMessage()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return super().filter(record)


def install_filter():
    # Logger filters do not apply to descendant records; protect every configured output handler as well.
    outputs = [*logging.getLogger().handlers, logging.getLogger("odoo.http"), logging.getLogger("odoo.http.server")]
    for output in outputs:
        if not any(isinstance(item, EditingCallbackFilter) for item in output.filters):
            output.addFilter(EditingCallbackFilter())


def record_staged_document(session_id, object_key, sha256, size):
    """Privileged recovery evidence, emitted before a flush/commit can erase the object's database association."""
    if not request:
        return
    evidence = request.httprequest.environ.get(CALLBACK_REQUEST_EVIDENCE, {})
    if evidence.get("session_id") != session_id or not evidence.get("validated_save"):
        return
    _logger.info(
        "ONLYOFFICE callback staged_bytes session_id=%s object_key=%s sha256=%s size=%s correlation_id=%s",
        session_id,
        object_key,
        sha256,
        size,
        evidence["correlation"],
    )
