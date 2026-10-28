"""The browser boundary uses the existing editing model and explicitly configured service origins."""

import ipaddress
import json
import os
import re
from urllib.parse import urlsplit

from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_PREFIX,
    EDITING_UNAVAILABLE,
    INTERNAL_URL_VARIABLE,
    PUBLIC_URL_VARIABLE,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_WRITE, NOT_FOUND, PERMISSION_DENIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.request_env import request_env

CALLBACK_ORIGIN_VARIABLE = "ONLYOFFICE_CALLBACK_ORIGIN"
EDITOR_PATH = re.compile(r"/medilab/laboratory-files/((?a:\d+))/edit\Z")
INVALID_SERVICE_ORIGIN = "Invalid service origin"

ASSETS = "/sol_laboratory/static/src/laboratory_files/editor/"


def _local_service_host(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host):
            raise ValueError(INVALID_SERVICE_ORIGIN) from None
        if any(not label or label.startswith("-") or label.endswith("-") for label in host.split(".")):
            raise ValueError(INVALID_SERVICE_ORIGIN)
        if re.fullmatch(r"(?:(?a:\d+)|0[xX][0-9a-fA-F]+)", host.rsplit(".", 1)[-1]):
            raise ValueError("Ambiguous IP address")
        return host.lower() == "localhost"


def configured_origin(value, *, private=False):
    """Only origins, without URL syntax browsers or proxies could interpret differently. Public HTTP is local only."""
    if not isinstance(value, str) or not value or any(c.isspace() or not c.isprintable() for c in value):
        raise ValueError(INVALID_SERVICE_ORIGIN)
    if any(c in value for c in ("\\", "%", "@", "?", "#")):
        raise ValueError(INVALID_SERVICE_ORIGIN)
    parts = urlsplit(value)
    host = parts.hostname or ""
    if (
        parts.scheme not in ("http", "https")
        or not host
        or parts.path not in ("", "/")
        or parts.port == 0
        or parts.netloc.endswith(":")
    ):
        raise ValueError(INVALID_SERVICE_ORIGIN)
    local = _local_service_host(host)
    if parts.scheme == "http" and not (private or local):
        raise ValueError("Public services require TLS")
    return f"{parts.scheme}://{parts.netloc.lower()}"


def page_headers(response, public_origin="", bucket_origin=""):
    connections = " ".join(dict.fromkeys(filter(None, (public_origin, bucket_origin))))
    frames = public_origin or "'none'"
    response.headers.update(
        {
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": (
                "default-src 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'self'; "
                f"script-src 'self' {public_origin}; frame-src {frames}; "
                f"connect-src 'self' {connections}; style-src 'self'; img-src 'self'; form-action 'self'"
            ),
        }
    )
    return response


def render_page(status, *, message="", retry_path="", config=None, public_origin="", bucket_origin=""):
    env = request_env()
    response = request.render(
        "sol_laboratory.laboratory_editor_page",
        {
            "config_json": json.dumps(config, ensure_ascii=True) if config else "",
            "title": config["document"]["title"] if config else "",
            "message": message,
            "retry_path": retry_path,
            "script_url": public_origin + "/web-apps/apps/api/documents/api.js" if config else "",
            "assets": ASSETS,
            "language": (env.lang or "en_US").replace("_", "-"),
        },
        status=status,
    )
    response.flatten()
    return page_headers(response, public_origin if config else "", bucket_origin if config else "")


def editor_origins():
    public = configured_origin(os.environ.get(PUBLIC_URL_VARIABLE))
    callback = configured_origin(os.environ.get(CALLBACK_ORIGIN_VARIABLE), private=True)
    configured_origin(os.environ.get(INTERNAL_URL_VARIABLE), private=True)
    bucket = laboratory_bucket.settings()
    bucket_origin = configured_origin(bucket.public_address if bucket else None)
    configured_origin(bucket.address if bucket else None, private=True)
    return public, callback, bucket_origin


def open_editor(file_id):
    env = request_env()
    path = f"/medilab/laboratory-files/{file_id}/edit"
    file = env[MODEL_LABORATORY_FILE].browse(file_id)
    missing = env._("This file does not exist or you do not have access to it.")
    try:
        # A global permission refusal must not reveal existence through a different status for missing ids.
        env[MODEL_LABORATORY_FOLDER]._check_laboratory_files_permission()
        if not 0 < file_id < 2**31 or not file.sudo().exists():
            return render_page(404, message=missing)
        # Roll back a new/joined session if config generation or origin validation fails afterwards.
        with env.cr.savepoint():
            # Validate service configuration before any health-check request, after the model's disclosure checks.
            file._check_file_access(FILE_WRITE)
            file._check_can_edit_online()
            try:
                public, callback, bucket_origin = editor_origins()
            except ValueError:
                raise LaboratoryFileError(
                    EDITING_UNAVAILABLE, env._("Online editing is unavailable right now.")
                ) from None
            session = env[MODEL_LABORATORY_EDITING_SESSION]._open_for(file)
            config = session._editor_config(env.user, callback + CALLBACK_PREFIX + session._callback_token())
            return render_page(200, retry_path=path, config=config, public_origin=public, bucket_origin=bucket_origin)
    except LaboratoryFileError as error:
        if error.code == NOT_FOUND:
            return render_page(404, message=missing)
        status = {PERMISSION_DENIED: 403, EDITING_UNAVAILABLE: 503}.get(error.code, 409)
        return render_page(status, message=str(error), retry_path=path if status in (409, 503) else "")
    except AccessError:
        return render_page(403, message=env._("You do not have permission to edit this file."))
