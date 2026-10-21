"""The route every endpoint of the laboratory files API is declared with, and its answers and refusals.

A route checks the computer's key, the laboratory files permission and the request against the OpenAPI document before
its endpoint acts. A refusal is raised as a LaboratoryFileError with its code, and every exception of the API's paths
is answered in one format by ir.http, so a feature that adds routes adds only its endpoints and its codes."""

import dataclasses
import functools
import json
import logging
import re
import uuid
from datetime import UTC

from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound, Unauthorized

from odoo import http
from odoo.exceptions import AccessDenied, AccessError, ConcurrencyError, MissingError, UserError
from odoo.http import request
from odoo.http.session import SessionExpiredException
from odoo.sql_db import PG_CONCURRENCY_EXCEPTIONS_TO_RETRY

from odoo.addons.sol_laboratory.constants.laboratory_api import API_PREFIX, ERROR_STATUSES, TRY_AGAIN_SECONDS
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    INTERNAL_ERROR,
    INVALID_KEY,
    INVALID_REQUEST,
    METHOD_NOT_ALLOWED,
    NOT_FOUND,
    TRY_AGAIN,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.routes import DEVICE_KEY
from odoo.addons.sol_laboratory.services import openapi_document
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.request_env import request_env

_logger = logging.getLogger(__name__)

# The Authorization header as Odoo's bearer authentication reads it, so both read the same key. The key starts at the
# first character that is not a space, so the pattern cannot backtrack.
BEARER = re.compile(r"^bearer\s+(\S.*)$", re.IGNORECASE)
# The names of the arguments a route path gives, such as device_id in /devices/<int:device_id>/revoke.
PATH_ARGUMENT = re.compile(r"<(?:[^:<>]+:)?([^:<>]+)>")
# How the routes authenticate: computers by their key; signing in by the login it sends; health checks not at all.
BY_KEY = "bearer"
BY_LOGIN = "public"
UNAUTHENTICATED = "none"


def is_api_path(path):
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


def laboratory_api_route(path, methods, operation, auth=BY_KEY, permission=True, readonly=False):
    """Declare an endpoint of the API at the path under /medilab/api/v1, for the methods and the operation of the
    OpenAPI document with that operationId.

    A route by key finds the computer of the key and, with permission, checks the laboratory files permission; its
    endpoint gets the computer, the request's JSON body and the path's arguments. Other routes get the body and the
    arguments. An endpoint returns the JSON value it answers with, None for an answer without content, or a response."""
    declared = DeclaredRoute(methods, operation, PATH_ARGUMENT.findall(path), auth, permission)

    def decorator(endpoint):
        def route(controller, **params):
            return serve(endpoint, controller, params, declared)

        # The endpoint's name, so the routes of a controller keep theirs. Odoo passes a route only the arguments its
        # signature names, which would drop a query parameter the request check must refuse: the route takes them all.
        functools.update_wrapper(route, endpoint)
        del route.__wrapped__
        return http.route(
            API_PREFIX + path,
            type="http",
            auth=auth,
            methods=methods,
            csrf=False,
            save_session=False,
            readonly=readonly,
            **DEVICE_KEY,
        )(route)

    return decorator


@dataclasses.dataclass(frozen=True)
class DeclaredRoute:
    """What a route of the API was declared with: its methods, its operation of the OpenAPI document, the names of its
    path's arguments, how it authenticates and whether it checks the laboratory files permission."""

    methods: list
    operation: str
    arguments: list
    auth: str
    permission: bool


def serve(endpoint, controller, params, declared):
    """Serve a request of the endpoint once its method, its request, the computer of its key and the laboratory files
    permission pass, and answer what it returns."""
    methods = declared.methods
    # Odoo adds OPTIONS to every route's methods and serves HEAD as GET.
    if request.httprequest.method not in (*methods, *(["HEAD"] if "GET" in methods else [])):
        raise MethodNotAllowed(valid_methods=methods)
    path_arguments = {name: params.pop(name) for name in declared.arguments}
    body = checked_request(declared.operation, params)
    if declared.auth == BY_KEY:
        env = request_env()
        device = env[MODEL_LABORATORY_DEVICE]._from_key(bearer_key())
        if declared.permission:
            env[MODEL_LABORATORY_FOLDER]._check_laboratory_files_permission()
        result = endpoint(controller, device, body, **path_arguments)
    else:
        result = endpoint(controller, body, **path_arguments)
    if isinstance(result, http.Response):
        return result
    return json_answer(result)


def bearer_key():
    """The key of the call. Odoo's bearer authentication also takes a browser session without one, which the API never
    does: every call comes from a signed-in computer."""
    match = BEARER.match(request.httprequest.headers.get("Authorization") or "")
    if not match:
        raise LaboratoryFileError(INVALID_KEY, request_env()._("Sign this computer in: the call has no key."))
    return match.group(1)


def checked_request(operation, query):
    """The JSON body of the request once it matches the operation of the document: no query parameter the operation
    does not take, and a JSON body only where it takes one, matching its schema."""
    env = request_env()
    if query:
        raise LaboratoryFileError(INVALID_REQUEST, env._("This route takes no parameter %s.", ", ".join(sorted(query))))
    data = request.httprequest.get_data()
    pointer = openapi_document.request_body_pointer(operation)
    if pointer is None:
        if data:
            raise LaboratoryFileError(INVALID_REQUEST, env._("This route takes no body."))
        return None
    if request.httprequest.mimetype != "application/json":
        raise LaboratoryFileError(INVALID_REQUEST, env._("The body of this route is JSON."))
    try:
        body = json.loads(data)
    except ValueError as error:
        raise LaboratoryFileError(INVALID_REQUEST, env._("The body is not valid JSON.")) from error
    if error := openapi_document.schema_error(pointer, body):
        raise LaboratoryFileError(INVALID_REQUEST, env._("The request does not match the API: %s", error))
    return body


def json_answer(value, status=200, headers=None):
    if value is None and status == 200:
        return request.make_response(b"", status=204)
    return request.make_json_response(value, headers=headers, status=status)


def refusal_answer(code, message, retry_after=None, headers=None, error_id=None):
    """The answer of a refusal: its code and message, with the HTTP status of its code."""
    error = {"code": code, "message": message}
    if error_id:
        error["id"] = error_id
    headers = dict(headers or {})
    if retry_after:
        headers["Retry-After"] = str(retry_after)
    if ERROR_STATUSES[code] == 401:
        headers["WWW-Authenticate"] = "Bearer"
    return json_answer({"error": error}, ERROR_STATUSES[code], list(headers.items()))


def exception_answer(exception):
    """The answer of an exception raised while serving a path of the API. A request refused this way commits nothing,
    as Odoo commits only what an endpoint returns."""
    env = request_env()
    if isinstance(exception, LaboratoryFileError):
        return refusal_answer(exception.code, exception.args[0], exception.retry_after)
    if isinstance(exception, MethodNotAllowed):
        allowed = [method for method in exception.valid_methods or () if method not in ("OPTIONS", "HEAD")]
        return refusal_answer(
            METHOD_NOT_ALLOWED,
            env._("This route does not take the method %s.", request.httprequest.method),
            headers={"Allow": ", ".join(allowed)},
        )
    if isinstance(exception, (Unauthorized, AccessDenied, SessionExpiredException)):
        return refusal_answer(INVALID_KEY, env._("This computer is not signed in."))
    # A record the person may not read answers as one that does not exist, so the answer does not tell that it does.
    if isinstance(exception, (NotFound, MissingError, AccessError)):
        return refusal_answer(NOT_FOUND, env._("Nothing is found at this address."))
    if isinstance(exception, UserError) or (
        isinstance(exception, HTTPException) and 400 <= (exception.code or 0) < 500
    ):
        return refusal_answer(INVALID_REQUEST, env._("The request cannot be done: %s", _description(exception)))
    if isinstance(exception, (ConcurrencyError, *PG_CONCURRENCY_EXCEPTIONS_TO_RETRY)):
        return refusal_answer(
            TRY_AGAIN, env._("The server is busy with the same records; try again."), TRY_AGAIN_SECONDS
        )
    error_id = uuid.uuid4().hex
    _logger.error("Laboratory files API error %s", error_id, exc_info=exception)
    return refusal_answer(
        INTERNAL_ERROR,
        env._("The server failed. Give this id to your administrator: %s", error_id),
        error_id=error_id,
    )


def _description(exception):
    if isinstance(exception, HTTPException):
        return exception.description or exception.name
    return exception.args[0] if exception.args else ""


def api_datetime(value):
    """A datetime of Odoo, which is in UTC, as the API gives it."""
    return value.replace(tzinfo=UTC).isoformat() if value else None
