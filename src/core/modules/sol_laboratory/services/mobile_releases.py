"""Select the Medilab Mobile release a phone must install from the catalog the release pipeline publishes, without
reading keys or fetching request-supplied addresses."""

import json
import re

from odoo.addons.sol_laboratory.constants.mobile_updates import (
    ACTION_UNAVAILABLE,
    CATALOG_VARIABLE,
    DOCUMENT_PATH,
    DOCUMENT_URI,
    KIND_CODE,
    PLATFORMS,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_CONFIG_PARAMETER
from odoo.addons.sol_laboratory.constants.settings import (
    MOBILE_MINIMUM_VERSION_PARAMETER,
    MOBILE_STOPPED_VERSIONS_PARAMETER,
)
from odoo.addons.sol_laboratory.services.sync_releases import (
    check_date,
    check_signature,
    read_catalog,
    safe_download_url,
    version_key,
)

RUNTIME_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
VERSION_SEPARATOR = re.compile(r"[\s,]+")


def parse_versions(value):
    """The semantic versions of a setting that lists them separated by commas or spaces."""
    return [version for version in VERSION_SEPARATOR.split(value or "") if version]


def served(env):
    """The oldest version MediLab serves, as a version key or None, and the keys of the versions it stops serving."""
    parameters = env[MODEL_IR_CONFIG_PARAMETER].sudo()
    minimum = parameters.get_str(MOBILE_MINIMUM_VERSION_PARAMETER)
    stopped = parse_versions(parameters.get_str(MOBILE_STOPPED_VERSIONS_PARAMETER))
    return (version_key(minimum) if minimum else None), {version_key(version) for version in stopped}


def _check_release(release):
    check_date(release["pub_date"])
    if release["kind"] == KIND_CODE:
        manifest = json.loads(release["manifest"])
        # A manifest of another runtime would be served to phones it cannot run on.
        if not isinstance(manifest, dict) or manifest.get("runtimeVersion") != release["runtime_version"]:
            raise ValueError("Manifest of another runtime.")
        check_signature(release["signature"])
    elif not safe_download_url(release["url"]):
        raise ValueError("Unsafe artifact URL.")


def catalog():
    releases = read_catalog(CATALOG_VARIABLE, DOCUMENT_PATH, DOCUMENT_URI)
    seen = set()
    for release in releases:
        identity = (release["platform"], release["kind"], version_key(release["version"]))
        if identity in seen:
            raise ValueError("Ambiguous release catalog.")
        seen.add(identity)
        _check_release(release)
    return releases


def valid_platform(platform, runtime_version):
    return platform in PLATFORMS and bool(RUNTIME_VERSION.fullmatch(runtime_version))


def check_platform(platform, runtime_version):
    if not valid_platform(platform, runtime_version):
        raise ValueError("Unsupported release platform.")


def _eligible(releases, platform, minimum, stopped):
    for release in releases:
        key = version_key(release["version"])
        if release["platform"] == platform and key not in stopped and (minimum is None or key >= minimum):
            yield release


def release_answer(platform, runtime_version, version, minimum, stopped):
    """What the phone does before it is used, or None when it runs a version MediLab serves and has nothing newer. A
    code update runs only on the runtime it was built for; any other phone needs the install."""
    check_platform(platform, runtime_version)
    current = version_key(version)
    releases = catalog()
    newer = [
        release
        for release in _eligible(releases, platform, minimum, stopped)
        if version_key(release["version"]) > current
        and (release["kind"] != KIND_CODE or release["runtime_version"] == runtime_version)
    ]
    if newer:
        # A code update and an install of the same version: the code update is the smaller download.
        release = max(newer, key=lambda value: (version_key(value["version"]), value["kind"] == KIND_CODE))
        if release["kind"] == KIND_CODE:
            return {"action": KIND_CODE, "version": release["version"]}
        return {key: release[key] for key in ("version", "url", "sha256")} | {"action": release["kind"]}
    # A platform without releases, such as iOS before its first, is never refused.
    if minimum is not None and current < minimum and any(release["platform"] == platform for release in releases):
        return {"action": ACTION_UNAVAILABLE}
    return None


def code_update(platform, runtime_version, minimum, stopped):
    """The newest eligible code release of the runtime, or None."""
    check_platform(platform, runtime_version)
    releases = [
        release
        for release in _eligible(catalog(), platform, minimum, stopped)
        if release["kind"] == KIND_CODE and release["runtime_version"] == runtime_version
    ]
    return max(releases, key=lambda value: version_key(value["version"])) if releases else None
