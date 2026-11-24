import hashlib
import io
import logging

import xlsxwriter

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket

_logger = logging.getLogger(__name__)


def xlsx_content(text):
    stream = io.BytesIO()
    with xlsxwriter.Workbook(stream, {"in_memory": True}) as workbook:
        sheet = workbook.add_worksheet()
        sheet.write_string(0, 0, text)
    return stream.getvalue()


def content_writer(env):
    """A function that writes demo file content to an object of its own and settles it: it returns the
    verified content, or with own the content of its own object, a duplicate when the bytes are stored
    already. With pending it writes the bytes and returns the pending content. The bytes go to the laboratory files
    bucket when the bucket answers, so the demo versions download and open online; without the bucket the demo still
    installs, and the objects are missing."""
    writes = laboratory_bucket.is_ready()
    if not writes:
        _logger.warning("The laboratory files bucket does not answer: the demo files are stored without their bytes.")
    contents = env[MODEL_LABORATORY_CONTENT].sudo()

    def store(value, own=False, pending=False):
        data = value if isinstance(value, bytes) else value.encode()
        content = contents._new_pending()
        if writes:
            laboratory_bucket.write(content.object_key, iter([data]))
        if pending:
            return content
        settled = content._settle(hashlib.sha256(data).hexdigest(), len(data))
        return content if own else settled

    store.writes = writes
    return store
