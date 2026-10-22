from odoo import models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FOLDER,
)


# Thư Mục Phòng Thí Nghiệm: what a computer reads of a folder to sync it, once the person may read the folder: its files
# with their current versions, and the changes to them after the last one the computer saw.
class LaboratoryFolderFeed(models.Model):
    _inherit = MODEL_LABORATORY_FOLDER

    def _files_after(self, after, limit):
        """The folder's files with an id above after, in the order of their ids, at most limit of them."""
        self.ensure_one()
        files = self.env[MODEL_LABORATORY_FILE].sudo()
        found = files.search([("folder_id", "=", self.id), ("id", ">", after)], order="id", limit=limit)
        return found.with_env(self.env)

    def _changes_after(self, after, limit):
        """The changes to the current versions of the folder's files with an id above after, in the order of their ids,
        at most limit of them. Every change commits before any of a higher id in the folder, so a computer that reads
        from the last one it saw misses none."""
        self.ensure_one()
        changes = self.env[MODEL_LABORATORY_FILE_CHANGE].sudo()
        found = changes.search([("folder_id", "=", self.id), ("id", ">", after)], order="id", limit=limit)
        return found.with_env(self.env)
