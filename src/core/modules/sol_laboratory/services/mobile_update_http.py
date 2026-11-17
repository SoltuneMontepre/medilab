"""Public Medilab Mobile release and Expo Updates answers; neither authenticates the phone."""

import uuid

from odoo.http import request

from odoo.addons.sol_laboratory.constants.mobile_updates import RELEASE_PREFIX, SIGNING_KEY_ID, UPDATES_PATH
from odoo.addons.sol_laboratory.constants.sync_updates import HEADERS
from odoo.addons.sol_laboratory.services import mobile_releases
from odoo.addons.sol_laboratory.services.request_env import request_env
from odoo.addons.sol_laboratory.services.sync_releases import version_key
from odoo.addons.sol_laboratory.services.sync_update_http import INVALID_UPDATE_REQUEST, answer, refusal

PROTOCOL_HEADERS = [("expo-protocol-version", "1")]


def is_mobile_update_path(path):
    return path in (UPDATES_PATH, RELEASE_PREFIX) or path.startswith(RELEASE_PREFIX + "/")


def _refused_request():
    """The refusal of a method other than GET or HEAD, or of a query or body, which neither route takes; None when the
    request is a plain read."""
    incoming = request.httprequest
    if incoming.method not in ("GET", "HEAD"):
        return refusal("method_not_allowed", "Use GET to check for updates.", 405, [("Allow", "GET, HEAD")])
    if incoming.args or incoming.content_length:
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    return None


def _unavailable():
    return refusal("update_unavailable", "Updates are unavailable. Contact your administrator.", 503)


def release(platform, runtime_version, version):
    if refused := _refused_request():
        return refused
    try:
        mobile_releases.check_platform(platform, runtime_version)
        version_key(version)
    except ValueError:
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    try:
        minimum, stopped = mobile_releases.served(request_env())
        result = mobile_releases.release_answer(platform, runtime_version, version, minimum, stopped)
    except (OSError, ValueError):
        return _unavailable()
    return answer(result)


def expo_update():
    if refused := _refused_request():
        return refused
    headers = request.httprequest.headers
    platform = headers.get("expo-platform", "")
    runtime_version = headers.get("expo-runtime-version", "")
    if headers.get("expo-protocol-version") != "1" or not mobile_releases.valid_platform(platform, runtime_version):
        return refusal("invalid_request", INVALID_UPDATE_REQUEST, 400)
    try:
        minimum, stopped = mobile_releases.served(request_env())
        update = mobile_releases.code_update(platform, runtime_version, minimum, stopped)
    except (OSError, ValueError):
        return _unavailable()
    if update is None:
        return answer(None, headers=PROTOCOL_HEADERS)
    # The manifest and its signature go out byte for byte as the release pipeline signed them.
    boundary = uuid.uuid4().hex
    part = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        'Content-Disposition: form-data; name="manifest"\r\n'
        f'expo-signature: sig="{update["signature"]}", keyid="{SIGNING_KEY_ID}"\r\n'
        "\r\n"
        f"{update['manifest']}\r\n"
        f"--{boundary}--\r\n"
    )
    return request.make_response(
        part.encode(),
        headers=[
            *HEADERS,
            *PROTOCOL_HEADERS,
            ("expo-sfv-version", "0"),
            ("Content-Type", f"multipart/mixed; boundary={boundary}"),
        ],
    )
