"""The path of the laboratory files API, the HTTP status of each code it refuses with, and the limits on signing in."""

from datetime import timedelta

from odoo.addons.sol_laboratory.constants.laboratory_editing import EDITING_UNAVAILABLE, NOT_EDITABLE
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_REVOKED,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    INTERNAL_ERROR,
    INVALID_CREDENTIALS,
    INVALID_KEY,
    INVALID_REQUEST,
    LOCKED,
    METHOD_NOT_ALLOWED,
    NOT_ELIGIBLE,
    NOT_FOUND,
    NOT_LOCKABLE,
    NOT_LOCKED,
    PERMISSION_DENIED,
    TOO_MANY_ATTEMPTS,
    TRY_AGAIN,
)

# Every route of the API is under this path.
API_PREFIX = "/medilab/api/v1"
# The HTTP status each refusal answers with. A feature that adds a code adds it here and to the OpenAPI document.
ERROR_STATUSES = {
    INVALID_REQUEST: 400,
    INVALID_CREDENTIALS: 401,
    INVALID_KEY: 401,
    PERMISSION_DENIED: 403,
    DEVICE_REVOKED: 403,
    NOT_FOUND: 404,
    METHOD_NOT_ALLOWED: 405,
    FOLDER_ARCHIVED: 409,
    FOLDER_DISABLED: 409,
    LOCKED: 409,
    NOT_LOCKED: 409,
    NOT_ELIGIBLE: 422,
    NOT_LOCKABLE: 422,
    NOT_EDITABLE: 422,
    TOO_MANY_ATTEMPTS: 429,
    INTERNAL_ERROR: 500,
    TRY_AGAIN: 503,
    EDITING_UNAVAILABLE: 503,
}
# Seconds a computer waits before calling again after try_again.
TRY_AGAIN_SECONDS = 5
# Failed sign-ins of a login that are not slowed; each one after them waits a delay that doubles from the first one up to
# the longest one, counted from the last failure.
FREE_SIGN_IN_FAILURES = 5
FIRST_SIGN_IN_DELAY = 1
LONGEST_SIGN_IN_DELAY = 60
# The failures of a login are forgotten once its last one is this old.
SIGN_IN_FAILURE_WINDOW = timedelta(minutes=15)
