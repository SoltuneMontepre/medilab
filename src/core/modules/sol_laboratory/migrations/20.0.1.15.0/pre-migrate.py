import logging
from collections import defaultdict

from odoo.exceptions import UserError
from odoo.tools.sql import table_exists

from odoo.addons.sol_laboratory.services.laboratory_paths import normal_pattern

_logger = logging.getLogger(__name__)

CONFLICTS_HEADING = (
    "Laboratory sync rules of one kind and pattern differ in their flags. Keep one rule of each group below, or change "
    "the pattern of the others, in Laboratory > Documents > Sync Rules, then upgrade again."
)


def migrate(cr, _version):
    # A folder has one sync rule of each kind and pattern, the pattern as the model keeps it. Before the unique key is
    # added, the rules of one kind and pattern become the oldest of them, with its pattern made normal, when their flags
    # are the same; when they differ, the upgrade is refused before any rule changes, for an administrator to choose.
    # The lock keeps a worker still running the old code from adding a rule meanwhile, until the upgrade commits.
    if not table_exists(cr, "medilab_laboratory_sync_rule"):
        return
    cr.execute("LOCK TABLE medilab_laboratory_sync_rule IN SHARE ROW EXCLUSIVE MODE")
    cr.execute(
        """
        SELECT rule.id, rule.folder_id, folder.name AS folder_name, rule.kind, rule.pattern, rule.recursive,
               rule.enabled
          FROM medilab_laboratory_sync_rule rule
          JOIN medilab_laboratory_folder folder ON folder.id = rule.folder_id
      ORDER BY rule.id
        """
    )
    groups = defaultdict(list)
    for rule in cr.dictfetchall():
        groups[rule["folder_id"], rule["kind"], normal_pattern(rule["kind"], rule["pattern"])].append(rule)
    conflicts = {key: rules for key, rules in groups.items() if len({_flags(rule) for rule in rules}) > 1}
    if conflicts:
        raise UserError(_conflicts_message(conflicts))
    for (folder_id, kind, pattern), (oldest, *others) in groups.items():
        for rule in others:
            _logger.warning(
                "Deleted sync rule %s of laboratory folder %s, a second %s rule %r: include subfolders %s, enabled %s.",
                rule["id"],
                folder_id,
                kind,
                pattern,
                *_flags(rule),
            )
        if others:
            cr.execute("DELETE FROM medilab_laboratory_sync_rule WHERE id = ANY(%s)", [[rule["id"] for rule in others]])
        if oldest["pattern"] != pattern:
            cr.execute("UPDATE medilab_laboratory_sync_rule SET pattern = %s WHERE id = %s", [pattern, oldest["id"]])


def _flags(rule):
    return bool(rule["recursive"]), bool(rule["enabled"])


def _conflicts_message(conflicts):
    lines = [CONFLICTS_HEADING]
    for (folder_id, kind, pattern), rules in conflicts.items():
        flags = ", ".join(
            "rule {} (include subfolders {}, enabled {})".format(rule["id"], *_flags(rule)) for rule in rules
        )
        lines.append(f"Folder {folder_id} {rules[0]['folder_name']!r}, {kind} {pattern!r}: {flags}")
    return "\n".join(lines)
