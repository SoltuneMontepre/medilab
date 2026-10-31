"""The native ONLYOFFICE HTTP boundary. The models validate identity, authorize saves and store versions."""

import json
import logging
import time
import uuid

from werkzeug.exceptions import MethodNotAllowed, NotFound

from odoo.api import SUPERUSER_ID
from odoo.exceptions import ConcurrencyError
from odoo.http import request
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_AUDIT_CONTEXT,
    CALLBACK_AUDIT_ORIGIN,
    CALLBACK_DOCUMENT_PATH,
    CALLBACK_DOCUMENT_URI,
    CALLBACK_LOGGER,
    CALLBACK_PREFIX,
    CALLBACK_READY_TO_SAVE,
    CALLBACK_REQUEST_EVIDENCE,
    ERROR,
    JWT_HEADER,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION
from odoo.addons.sol_laboratory.services import openapi_document
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import EditingCallbackRefused
from odoo.addons.sol_laboratory.services.record_id import persisted_id
from odoo.addons.sol_laboratory.services.request_env import request_env

_logger = logging.getLogger(CALLBACK_LOGGER)
PAYLOAD_SCHEMA = "/components/schemas/CallbackFields"
RESPONSE_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


class CallbackRefused(Exception):
    def __init__(self, status, outcome="refused"):
        super().__init__(status)
        self.status = status
        self.outcome = outcome


def is_callback_path(path):
    return path.startswith(CALLBACK_PREFIX)


def callback_answer(status=200, headers=None):
    return request.make_json_response(
        {"error": 0 if status == 200 else 1}, headers={**RESPONSE_HEADERS, **(headers or {})}, status=status
    )


def callback_body():
    if request.httprequest.mimetype != "application/json":
        raise CallbackRefused(400)
    try:
        body = json.loads(request.httprequest.get_data(cache=True))
    except ValueError:
        raise CallbackRefused(400) from None
    if not isinstance(body, dict):
        raise CallbackRefused(400)
    return body


def check_fields(fields):
    if openapi_document.schema_error(
        PAYLOAD_SCHEMA, fields, document_path=CALLBACK_DOCUMENT_PATH, document_uri=CALLBACK_DOCUMENT_URI
    ):
        raise CallbackRefused(400)


def serve_callback(callback_token):
    # Odoo adds OPTIONS to route methods automatically; the native callback contract accepts POST only.
    if request.httprequest.method != "POST":
        raise MethodNotAllowed(valid_methods=["POST"])
    # Odoo reuses the HTTP request on retry. Keep only trusted incident context from its earlier verified attempt.
    evidence = request.httprequest.environ.setdefault(
        CALLBACK_REQUEST_EVIDENCE, {"correlation": uuid.uuid4().hex, "session_id": 0, "started": time.monotonic()}
    )
    started, correlation = evidence["started"], evidence["correlation"]
    env = request_env()
    try:
        body = callback_body()
        with env.cr.savepoint():
            try:
                session, fields = env[MODEL_LABORATORY_EDITING_SESSION]._from_callback(
                    callback_token, body, request.httprequest.headers.get(JWT_HEADER)
                )
            except EditingCallbackRefused as refusal:
                # Reject the expired JWT without touching the model. A fresh, signed DS delivery may retry the save.
                if refusal.expired and evidence.get("validated_save"):
                    raise CallbackRefused(503, "delivery_expired") from None
                raise CallbackRefused(403) from None
            evidence["session_id"] = session.id
            check_fields(fields)
            evidence["validated_save"] = fields["status"] == CALLBACK_READY_TO_SAVE
            # auth='none' has no env user. Service writes need one, but the checked editor still authorizes the version.
            session = session.with_user(SUPERUSER_ID).with_context(**{CALLBACK_AUDIT_CONTEXT: CALLBACK_AUDIT_ORIGIN})
            try:
                handled = session._receive_callback(fields)
            except EditingCallbackRefused:
                raise CallbackRefused(400) from None
            status = 200 if handled else 503
            if not handled:
                outcome = "temporary_failure"
            elif session.status == ERROR:
                outcome = "terminal_error"
            else:
                outcome = session.status
            session_id = persisted_id(session)
        elapsed = time.monotonic() - started
        # A response is not yet a committed outcome: a flush/commit conflict may still make Odoo retry the request.
        env.cr.postcommit.add(lambda: log_outcome(status, outcome, correlation, session_id, elapsed))
        return callback_answer(status)
    except CallbackRefused as refusal:
        log_outcome(refusal.status, refusal.outcome, correlation, evidence["session_id"], time.monotonic() - started)
        return callback_answer(refusal.status)


def exception_answer(exception):
    """Called by ir.http after the outer request retry loop, never in place of that loop."""
    headers = None
    if isinstance(exception, MethodNotAllowed):
        status, outcome = 405, "method_not_allowed"
        headers = {"Allow": "POST"}
    elif isinstance(exception, NotFound):
        status, outcome = 404, "not_found"
    elif isinstance(exception, (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY)):
        status, outcome = 503, "concurrency_failure"
    else:
        status, outcome = 500, "internal_error"
    evidence = request.httprequest.environ.get(CALLBACK_REQUEST_EVIDENCE, {})
    elapsed = time.monotonic() - evidence["started"] if "started" in evidence else 0
    log_outcome(
        status,
        outcome,
        evidence.get("correlation", uuid.uuid4().hex),
        evidence.get("session_id", 0),
        elapsed=elapsed,
        error_type=type(exception).__name__,
    )
    return callback_answer(status, headers)


def log_outcome(status, outcome, correlation, session_id=0, elapsed=0, error_type="none"):
    level = logging.WARNING if status >= 400 or outcome == "terminal_error" else logging.INFO
    _logger.log(
        level,
        "ONLYOFFICE callback status=%s outcome=%s session_id=%s elapsed_seconds=%.3f correlation_id=%s error_type=%s",
        status,
        outcome,
        session_id,
        elapsed,
        correlation,
        error_type,
    )
