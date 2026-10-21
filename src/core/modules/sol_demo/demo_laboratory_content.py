import hashlib
import logging

from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket

_logger = logging.getLogger(__name__)


def content_writer(env):
    """A function that stores the text of a demo file as verified content and returns it. Its bytes are written to the
    laboratory files bucket when the bucket answers, so the demo versions download and open online; without the bucket
    the demo still installs, and the versions' objects are missing."""
    writes = laboratory_bucket.is_ready()
    if not writes:
        _logger.warning("The laboratory files bucket does not answer: the demo files are stored without their bytes.")
    contents = env[MODEL_LABORATORY_CONTENT].sudo()

    def store(text):
        data = text.encode()
        content = contents._new_pending()
        if writes:
            laboratory_bucket.write(content.object_key, iter([data]))
        return content._settle(hashlib.sha256(data).hexdigest(), len(data))

    return store
