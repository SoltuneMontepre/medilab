"""Validate the selected Sync endpoint using public readiness and unauthenticated API requests only."""

import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

from host_tools import HostError

MAX_RESPONSE = 65536


def validate_url(value):
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise HostError("The selected Odoo URL is invalid.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(character.isspace() or ord(character) < 32 for character in value)
        or "\\" in value
        or "@" in parsed.netloc
        or any(piece in {".", ".."} for piece in parsed.path.split("/"))
        or any(
            encoded in value.lower()
            for encoded in (
                "%2f",
                "%5c",
                "%2e",
                "%00",
                "%0a",
                "%0d",
                "%09",
                "%3f",
                "%23",
            )
        )
        or (port is not None and not 0 < port <= 65535)
    ):
        raise HostError(
            "Use an HTTP(S) Odoo base URL without credentials, query, fragment or unsafe path segments."
        )
    try:
        local = (
            parsed.hostname == "localhost"
            or ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        local = False
    if not local:
        raise HostError(
            "Sync setup verification requires the selected local Odoo origin (localhost or a loopback address)."
        )
    return value.rstrip("/")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _request, _file, _code, _message, _headers, _url):
        return None


def request_json(url, headers=None):
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", **(headers or {})}, method="GET"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        response = opener.open(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HostError(
            "The selected Odoo API is unreachable. Start the selected stack and check its URL/TLS configuration."
        ) from error
    with response:
        body = response.read(MAX_RESPONSE + 1)
        if (
            len(body) > MAX_RESPONSE
            or response.headers.get_content_type() != "application/json"
        ):
            raise HostError(
                "The selected Odoo API did not return bounded JSON; redirects and HTML login pages are not readiness."
            )
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError) as error:
            raise HostError("The selected Odoo API returned invalid JSON.") from error
        return response.status, value, response.headers


def verify(base, request=request_json):
    base = validate_url(base)
    for suffix in ("health", "ready"):
        status, value, _headers = request(f"{base}/medilab/api/v1/{suffix}")
        if (
            status != 200
            or not isinstance(value, dict)
            or value.get("status") != "pass"
        ):
            raise HostError(
                f"The Laboratory files API /{suffix} check failed. Install/configure sol_laboratory in the selected database."
            )
        if suffix == "ready":
            checks = value.get("checks")
            if (
                not isinstance(checks, dict)
                or not checks
                or any(result != "pass" for result in checks.values())
            ):
                raise HostError(
                    "The Laboratory files API readiness checks did not all pass."
                )
    for headers in ({}, {"Authorization": "Bearer medilab-setup-invalid-probe"}):
        status, value, response_headers = request(
            f"{base}/medilab/api/v1/devices", headers
        )
        refusal = value.get("error") if isinstance(value, dict) else None
        if (
            status != 401
            or not isinstance(refusal, dict)
            or refusal.get("code") != "invalid_key"
            or not isinstance(refusal.get("message"), str)
            or not refusal["message"].strip()
            or response_headers.get("WWW-Authenticate") != "Bearer"
        ):
            raise HostError(
                "The Laboratory files API must refuse unauthenticated device access with its documented Bearer/invalid_key response."
            )
    return base
