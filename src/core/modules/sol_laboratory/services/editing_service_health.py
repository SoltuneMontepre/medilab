"""Asks ONLYOFFICE Document Server, at its internal address, whether it edits documents, through its own health check.
Opening a file online asks it; the readiness of the laboratory files API never does."""

import logging
import os

import requests

from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE

_logger = logging.getLogger(__name__)

HEALTH_PATH = "/healthcheck"
# Seconds an open waits for the answer before it is refused.
TIMEOUT = 3


def is_editing_service_up():
    """True when the editing service answers its health check with true."""
    service_url = os.environ.get(INTERNAL_URL_VARIABLE)
    if not service_url:
        return False
    try:
        response = requests.get(f"{service_url.rstrip('/')}{HEALTH_PATH}", timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as error:
        _logger.warning("The editing service does not answer its health check: %s", type(error).__name__)
        return False
    return response.status_code == 200 and response.text.strip() == "true"
