import logging

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.tools.sql import table_exists

from odoo.addons.sol_laboratory.constants.models import MODEL_PARAMETER_METHOD

_logger = logging.getLogger(__name__)

SNAPSHOT_TABLE = "medilab_is_accredited_upgrade_snapshot"


def migrate(cr, _version):
    # Recompute under certificate rules and compare with the pre-migrate snapshot.
    # Manually assigned True values that no certificate supports become False; the
    # laboratory does not invent certificates to preserve them.
    # Snapshot retention: kept in {SNAPSHOT_TABLE} for verification of True→False
    # transitions. Drop it after accepting the upgrade, or rely on uninstall_hook
    # when uninstalling sol_laboratory.
    if not table_exists(cr, "medilab_parameter_method"):
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False})
    pairs = env[MODEL_PARAMETER_METHOD].search([])
    pairs._recompute_is_accredited()
    if not table_exists(cr, SNAPSHOT_TABLE):
        _logger.info("No accreditation upgrade snapshot; recomputed %s pairs.", len(pairs))
        return
    cr.execute(f"SELECT pair_id, old_value FROM {SNAPSHOT_TABLE}")
    snapshot = dict(cr.fetchall())
    flipped_true_to_false = []
    flipped_false_to_true = []
    for pair in pairs:
        old = snapshot.get(pair.id)
        if old is None:
            continue
        if old and not pair.is_accredited:
            flipped_true_to_false.append(pair.id)
        elif not old and pair.is_accredited:
            flipped_false_to_true.append(pair.id)
    _logger.info(
        "Accreditation upgrade recompute: %s pairs; True→False %s; False→True %s. Snapshot retained in %s.",
        len(pairs),
        flipped_true_to_false,
        flipped_false_to_true,
        SNAPSHOT_TABLE,
    )
