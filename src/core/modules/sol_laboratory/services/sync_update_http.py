"""Public updater and legacy refusal responses; neither authenticates an old device."""

import os

from werkzeug.exceptions import HTTPException, MethodNotAllowed, NotFound

from odoo.http import request

from odoo.addons.sol_laboratory.constants.sync_updates import DOWNLOAD_VARIABLE, HEADERS, LEGACY_PREFIX, UPDATE_PREFIX
from odoo.addons.sol_laboratory.services import sync_releases

INVALID_UPDATE_REQUEST = "Invalid update request."


def is_public_sync_path(path):
    return any(path == prefix or path.startswith(prefix + "/") for prefix in (LEGACY_PREFIX, UPDATE_PREFIX))


def exception_answer(exception):
    if isinstance(exception, MethodNotAllowed):
        return refusal("method_not_allowed", "Use GET to check for updates.", 405, [("Allow", "GET, HEAD")])
    if isinstance(exception, NotFound):
        return refusal("not_found", "No update route at this address.", 404)
    if isinstance(exception, HTTPException) and (exception.code or 500) < 500:
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    return refusal("internal_error", "Updates are unavailable. Contact your administrator.", 500)


def answer(value=None, status=200, headers=()):
    headers = [*HEADERS, *headers]
    if value is None:
        return request.make_response(b"", headers=headers, status=204 if status == 200 else status)
    return request.make_json_response(value, headers=headers, status=status)


def refusal(code, message, status, headers=()):
    return answer({"error": {"code": code, "message": message}}, status, headers)


def legacy_refusal():
    error = {
        "code": "client_update_required",
        "message": "Install the current MediLab Sync release. Keep application data and sign in again.",
    }
    download = os.environ.get(DOWNLOAD_VARIABLE)
    if sync_releases.safe_download_url(download):
        error["download_url"] = download
    return answer({"error": error}, 410)


def update(target, arch, version, trust="current"):
    incoming = request.httprequest
    if incoming.method not in ("GET", "HEAD"):
        return refusal("method_not_allowed", "Use GET to check for updates.", 405, [("Allow", "GET, HEAD")])
    parameters = incoming.args
    if (
        set(parameters) - {"channel"}
        or any(len(parameters.getlist(key)) != 1 for key in parameters)
        or incoming.content_length
    ):
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    channel = parameters.get("channel", "stable")
    try:
        sync_releases.request_key(target, arch, version, channel)
    except ValueError:
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    try:
        result = sync_releases.manifest(target, arch, version, channel, trust)
    except (OSError, ValueError):
        return refusal("update_unavailable", "Updates are unavailable. Contact your administrator.", 503)
    return answer(result)
