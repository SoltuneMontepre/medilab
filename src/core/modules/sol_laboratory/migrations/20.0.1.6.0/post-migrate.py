import logging

from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_TASK

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # Tasks now say whether the system linked them, and only those act on their document with full rights. A task that
    # predates this is trusted only when the audit trail proves it; the others wait for an administrator's review.
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env[MODEL_TASK]
    verified = tasks._verify_links_from_history()
    review = tasks._link_review()
    _logger.info("%s tasks verified as linked by the system from the audit trail.", len(verified))
    if review:
        _logger.warning(
            "%s tasks need an administrator's review before the system trusts them; see the Reviewing task links "
            "workflow. Tasks: %s",
            len(review),
            ", ".join(f"{row['task_id']} ({row['finding']})" for row in review),
        )
