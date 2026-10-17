import logging

from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)

SNAPSHOT_TABLE = "medilab_is_accredited_upgrade_snapshot"
# Completion marker so a zero-row snapshot is still retry-safe.
SNAPSHOT_MARKER = "medilab_is_accredited_upgrade_snapshot_done"


def migrate(cr, version):
    # Snapshot hand-set is_accredited values before the field becomes a stored compute.
    # Production upgrades clear unsupported manually assigned True values in post-migrate;
    # this table keeps the evidence of True→False transitions for verification.
    # Retention: kept after upgrade for verification; uninstall_hook drops it; safe to
    # DROP TABLE manually after the upgrade has been accepted.
    if not table_exists(cr, "medilab_parameter_method"):
        return
    if table_exists(cr, SNAPSHOT_MARKER):
        _logger.info("Accreditation upgrade snapshot already present; leaving it unchanged.")
        return
    cr.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SNAPSHOT_TABLE} (
            pair_id integer PRIMARY KEY,
            old_value boolean NOT NULL,
            snapped_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    cr.execute(
        f"""
        INSERT INTO {SNAPSHOT_TABLE} (pair_id, old_value)
        SELECT id, COALESCE(is_accredited, FALSE)
          FROM medilab_parameter_method
        ON CONFLICT (pair_id) DO NOTHING
        """
    )
    cr.execute(
        f"""
        SELECT COUNT(*),
               COUNT(*) FILTER (WHERE old_value),
               COUNT(*) FILTER (WHERE NOT old_value)
          FROM {SNAPSHOT_TABLE}
        """
    )
    total, true_count, false_count = cr.fetchone()
    cr.execute(
        """
        SELECT COUNT(*)
          FROM medilab_parameter_method
         WHERE subcontractor_id IS NOT NULL AND COALESCE(is_accredited, FALSE)
        """
    )
    subcontracted_true = cr.fetchone()[0]
    cr.execute(
        f"""
        CREATE TABLE {SNAPSHOT_MARKER} (
            completed_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    cr.execute(f"INSERT INTO {SNAPSHOT_MARKER} DEFAULT VALUES")
    _logger.info(
        "Accreditation upgrade snapshot: %s pairs (%s True, %s False, %s subcontracted True).",
        total,
        true_count,
        false_count,
        subcontracted_true,
    )
