"""Files Medilab Mobile sends in the JSON body of a request, as base64."""

import base64
import binascii

from odoo.addons.sol_laboratory.constants.laboratory_files import INVALID_REQUEST
from odoo.addons.sol_laboratory.constants.medilab_mobile import TOO_LARGE
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


def decoded_size(data: str) -> int:
    """The size of the base64 once decoded, worked out without decoding it."""
    return len(data) * 3 // 4 - data[-2:].count("=")


def decoded_base64(data: str, max_bytes: int, too_large: str, invalid: str) -> bytes:
    """The bytes of the base64, refused with the too_large message before decoding when over the limit, and with the
    invalid message when it is not base64."""
    if decoded_size(data) > max_bytes:
        raise LaboratoryFileError(TOO_LARGE, too_large)
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error as error:
        raise LaboratoryFileError(INVALID_REQUEST, invalid) from error
