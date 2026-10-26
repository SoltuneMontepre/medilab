"""Select owner-published signed artifacts without reading keys or fetching request-supplied URLs."""

import base64
import ipaddress
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from odoo.addons.sol_laboratory.constants.sync_updates import CATALOG_VARIABLE, DOCUMENT_PATH, DOCUMENT_URI
from odoo.addons.sol_laboratory.services import openapi_document

SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
CHANNEL = re.compile(r"[a-z][a-z0-9-]{0,31}")
MAX_CATALOG_BYTES = 1024 * 1024


def version_key(version):
    if not isinstance(version, str) or len(version) > 128 or not (match := SEMVER.fullmatch(version)):
        raise ValueError("Invalid semantic version.")
    prerelease = match[4]
    identifiers = []
    for part in prerelease.split(".") if prerelease else ():
        if part.isdigit() and len(part) > 1 and part.startswith("0"):
            raise ValueError("Invalid semantic version.")
        identifiers.append((0, int(part)) if part.isdigit() else (1, part))
    return (*map(int, match.group(1, 2, 3)), prerelease is None, tuple(identifiers))


def safe_download_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    decoded = unquote(value)
    if any(ord(char) < 33 or ord(char) == 127 or char == "\\" for char in decoded):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if not hostname or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        return False
    if port == 0 or any(part in (".", "..") for part in unquote(parsed.path).split("/")):
        return False
    if re.search(r"%25|%2f|%5c|%3f|%23", value, re.IGNORECASE):
        return False
    if parsed.scheme == "https":
        return True
    try:
        loopback = hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = False
    return parsed.scheme == "http" and loopback


def catalog():
    path = os.environ.get(CATALOG_VARIABLE)
    if not path:
        raise ValueError("Release catalog is unavailable.")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_CATALOG_BYTES + 1)
    if len(raw) > MAX_CATALOG_BYTES:
        raise ValueError("Release catalog is too large.")
    releases = json.loads(raw)
    if openapi_document.schema_error(
        "/components/schemas/Catalog", releases, document_path=DOCUMENT_PATH, document_uri=DOCUMENT_URI
    ):
        raise ValueError("Invalid release catalog.")
    seen = set()
    for release in releases["releases"]:
        key = version_key(release["version"])
        identity = (release["target"], release["arch"], release["channel"], release["trust"], key)
        if identity in seen or (release["channel"] == "stable" and not key[3]):
            raise ValueError("Ambiguous or unstable release catalog.")
        seen.add(identity)
        if not safe_download_url(release["url"]):
            raise ValueError("Unsafe artifact URL.")
        if "pub_date" in release:
            date = datetime.fromisoformat(release["pub_date"].replace("Z", "+00:00"))
            if date.tzinfo is None:
                raise ValueError("Release date needs a time zone.")
        try:
            signature = base64.b64decode(release["signature"], validate=True)
        except ValueError as error:
            raise ValueError("Invalid artifact signature encoding.") from error
        if not signature:
            raise ValueError("Empty artifact signature.")
    return releases["releases"]


def request_key(target, arch, current, channel):
    current_key = version_key(current)
    if target not in ("linux", "windows", "darwin") or arch not in ("x86_64", "aarch64"):
        raise ValueError("Unsupported release platform.")
    if not CHANNEL.fullmatch(channel):
        raise ValueError("Invalid release channel.")
    return current_key


def manifest(target, arch, current, channel, trust):
    current_key = request_key(target, arch, current, channel)
    releases = [
        release
        for release in catalog()
        if release["target"] == target
        and release["arch"] == arch
        and release["channel"] == channel
        and release["trust"] == trust
        and version_key(release["version"]) > current_key
    ]
    if not releases:
        return None
    release = max(releases, key=lambda value: version_key(value["version"]))
    return {key: release[key] for key in ("version", "url", "signature", "notes", "pub_date") if key in release}
