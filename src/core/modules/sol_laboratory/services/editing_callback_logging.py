"""Keep the callback capability and debug request headers out of Odoo's HTTP access/error records."""

import logging
from urllib.parse import unquote

from odoo.http import request

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_LOGGER,
    CALLBACK_PREFIX,
    CALLBACK_REQUEST_EVIDENCE,
)

_logger = logging.getLogger(CALLBACK_LOGGER)
NETWORK_LOGGERS = ("urllib3", "requests", "botocore", "boto3", "s3transfer")


def references_callback(text):
    for _index in range(16):
        if CALLBACK_PREFIX in text:
            return True
        decoded = unquote(text)
        if decoded == text:
            return False
        text = decoded
    # Bound work on hostile input and redact when nested encoding remains ambiguous.
    return True


def _references_callback(record):
    # Watchdogs run outside the request context and put thread URLs in message arguments or exception chains.
    texts = [record.getMessage(), record.exc_text or "", record.stack_info or ""]
    if record.exc_info:
        texts.append(logging.Formatter().formatException(record.exc_info))
    return any(references_callback(text) for text in texts)


class EditingCallbackFilter(logging.Filter):
    def filter(self, record):
        line = getattr(record, "http_request_line", "")
        name = record.name or ""
        transport = any(name == prefix or name.startswith(prefix + ".") for prefix in ("odoo.http", *NETWORK_LOGGERS))
        callback = (
            references_callback(line)
            or (transport and request and request.httprequest.path.startswith(CALLBACK_PREFIX))
            or _references_callback(record)
        )
        if not callback:
            return True
        # The server already expanded debug headers and its colored message; replace all representations together.
        record.msg = "ONLYOFFICE callback HTTP status=%s"
        record.args = (getattr(record, "http_response_status", "-"),)
        record.http_request_line = CALLBACK_PREFIX + "[redacted]"
        record.http_headers = ()
        record.colored_message = record.getMessage()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


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
