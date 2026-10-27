"""Presigning uses network SDKs that can log signed URLs at DEBUG level."""

import logging
import re
from urllib.parse import unquote

from odoo.http import request

from odoo.addons.sol_laboratory.services.editing_callback_logging import NETWORK_LOGGERS
from odoo.addons.sol_laboratory.services.laboratory_editor_page import EDITOR_PATH

EDITOR_REFERENCE = re.compile(r"/medilab/laboratory-files/[0-9]+/edit(?:[?\s\"'<]|$)")


def references_editor(text):
    for _index in range(16):
        if EDITOR_REFERENCE.search(text):
            return True
        decoded = unquote(text)
        if decoded == text:
            return False
        text = decoded
    # Ambiguous deeply nested encoding is redacted rather than guessed at, with bounded filtering work.
    return True


class LaboratoryEditorFilter(logging.Filter):
    def filter(self, record):
        transport = any(
            record.name == name or record.name.startswith(name + ".") for name in ("odoo.http", *NETWORK_LOGGERS)
        )
        active = transport and request and EDITOR_PATH.fullmatch(request.httprequest.path)
        text = " ".join(
            (
                record.getMessage(),
                getattr(record, "http_request_line", ""),
                getattr(record, "colored_message", ""),
                record.exc_text or "",
                record.stack_info or "",
            )
        )
        if record.exc_info:
            text += logging.Formatter().formatException(record.exc_info)
        if not active and not references_editor(text):
            return True
        record.msg = "Laboratory editor HTTP status=%s"
        record.args = (getattr(record, "http_response_status", "-"),)
        record.http_request_line = "/medilab/laboratory-files/[redacted]/edit"
        record.http_headers = ()
        record.colored_message = record.getMessage()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def install_editor_filter():
    for output in [
        *logging.getLogger().handlers,
        logging.getLogger("odoo.http"),
        logging.getLogger("odoo.http.server"),
    ]:
        if not any(isinstance(item, LaboratoryEditorFilter) for item in output.filters):
            output.addFilter(LaboratoryEditorFilter())
