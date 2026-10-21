import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, _version):
    # A folder has a category only when it has a sample. Folders of no sample lose theirs before the check is added; the
    # lock keeps a worker still running the old code from adding one meanwhile, until the upgrade commits.
    if not column_exists(cr, "medilab_laboratory_folder", "category"):
        return
    cr.execute("LOCK TABLE medilab_laboratory_folder IN SHARE ROW EXCLUSIVE MODE")
    cr.execute(
        """
        UPDATE medilab_laboratory_folder folder
           SET category = NULL
          FROM medilab_laboratory_folder old
         WHERE folder.id = old.id
           AND folder.sample_id IS NULL
           AND folder.category IS NOT NULL
     RETURNING folder.id, folder.root, old.category,
               (SELECT COUNT(*) FROM medilab_laboratory_file file WHERE file.folder_id = folder.id)
        """
    )
    for folder_id, root, category, file_count in sorted(cr.fetchall()):
        # Its files no longer count as that category: a former raw-data folder's files are locked and edited online.
        _logger.warning(
            "Cleared the category %s of laboratory folder %s (%s), which has no sample. Files in it: %s.",
            category,
            folder_id,
            root,
            file_count,
        )
