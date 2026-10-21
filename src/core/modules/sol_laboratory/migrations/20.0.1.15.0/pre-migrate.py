import logging

from odoo.tools.sql import table_exists

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # A folder has one sync rule of each kind and pattern. Before the unique key is added, the oldest rule of each stays
    # and the others are deleted; the lock keeps a worker still running the old code from adding one meanwhile, until
    # the upgrade commits.
    if not table_exists(cr, "medilab_laboratory_sync_rule"):
        return
    cr.execute("LOCK TABLE medilab_laboratory_sync_rule IN SHARE ROW EXCLUSIVE MODE")
    cr.execute(
        """
        DELETE FROM medilab_laboratory_sync_rule rule
         USING medilab_laboratory_sync_rule oldest
         WHERE oldest.folder_id = rule.folder_id
           AND oldest.kind = rule.kind
           AND oldest.pattern = rule.pattern
           AND oldest.id < rule.id
     RETURNING rule.id, rule.folder_id, rule.kind, rule.pattern, rule.recursive, rule.enabled
        """
    )
    for rule_id, folder_id, kind, pattern, recursive, enabled in sorted(cr.fetchall()):
        _logger.warning(
            "Deleted sync rule %s of laboratory folder %s, a second %s rule %r: include subfolders %s, enabled %s.",
            rule_id,
            folder_id,
            kind,
            pattern,
            recursive,
            enabled,
        )
