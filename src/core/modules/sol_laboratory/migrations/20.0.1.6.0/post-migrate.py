import logging

from odoo import api
from odoo.api import SUPERUSER_ID

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # Accreditation is worked out from certificates: a value set by hand that no certificate supports is cleared.
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    pairs = env[MODEL_PARAMETER_METHOD].search([])
    before = set(pairs.filtered("is_accredited").ids)
    pairs._recompute_is_accredited()
    after = set(pairs.filtered("is_accredited").ids)
    _logger.info(
        "Accreditation recomputed for %s pairs; no longer accredited: %s; now accredited: %s.",
        len(pairs),
        sorted(before - after),
        sorted(after - before),
    )
