from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_PERMISSION_MIXIN,
)


# Thay Đổi Tệp
class LaboratoryFileChange(models.Model):
    _name = MODEL_LABORATORY_FILE_CHANGE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Laboratory File Change"
    # The order computers read the changes in: a computer asks for those after the last id it saw.
    _order = "id"
    # Changes are only added, as files get new current versions.
    _permission_actions = ("read",)

    # The folder of the file.
    folder_id = fields.Many2one(
        MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="restrict", readonly=True
    )
    # The file whose current version changed.
    file_id = fields.Many2one(MODEL_LABORATORY_FILE, string="File", required=True, ondelete="restrict", readonly=True)
    # The new current version.
    version_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Version", required=True, ondelete="restrict", readonly=True
    )

    _folder_change_index = models.Index("(folder_id, id)")

    def write(self, vals):
        raise UserError(self.env._("The changes of laboratory files are only added, never changed."))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_change(self):
        raise UserError(self.env._("The changes of laboratory files are never deleted."))
