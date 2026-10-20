"""Checks the addresses the editing service gives for the documents it saved, so a call back cannot make Odoo fetch from
anywhere but the editing service."""

import os
from urllib.parse import urlsplit

from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE

# The port of each scheme Odoo fetches over when an address names none.
DEFAULT_PORTS = {"http": 80, "https": 443}


def is_editing_service_url(url, service_url):
    """True when the address is on the editing service reached at service_url: the same scheme, host and port, and no
    user name or password in it. An address with spaces, control characters or backslashes is refused, as the program
    that fetches it may read it differently from this check."""
    if not url or any(character.isspace() or not character.isprintable() or character == "\\" for character in url):
        return False
    try:
        target, service = urlsplit(url), urlsplit(service_url or "")
        scheme = target.scheme.lower()
        if scheme not in DEFAULT_PORTS or scheme != service.scheme.lower() or not service.hostname:
            return False
        return (
            target.hostname == service.hostname
            and (target.port or DEFAULT_PORTS[scheme]) == (service.port or DEFAULT_PORTS[scheme])
            and not (target.username or target.password)
        )
    except ValueError:
        # An address with a port that is not a number.
        return False


def is_saved_document_url(url):
    """True when the address is on the editing service set in the environment; false when none is set."""
    return is_editing_service_url(url, os.environ.get(INTERNAL_URL_VARIABLE))
