from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.services.laboratory_paths import is_relative_path, normal_text, path_key

# A file is found by its folder and path, which never change.
IDENTITY_FIELDS = ("folder_id", "path", "path_key")


# Tệp Phòng Thí Nghiệm
class LaboratoryFile(models.Model):
    _name = MODEL_LABORATORY_FILE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory File"
    _order = "folder_id, path, id"
    _rec_name = "path"
    # Files are made by saving their first version, are never renamed and never deleted.
    _permission_actions = ("read",)
    _audit_children = ("version_ids",)

    # The folder holding the file.
    folder_id = fields.Many2one(
        MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="restrict", readonly=True
    )
    # Path of the file relative to its folder, such as HPLC/run-01.csv, in the letter case it was first saved with.
    path = fields.Char(required=True, readonly=True)
    # The path in one Unicode form and one letter case; unique in the folder, so paths that differ only in letter case
    # are one file.
    path_key = fields.Char(compute="_compute_path_key", store=True, readonly=True)
    # The version people get; a restore adds a new version instead of pointing back at an old one.
    current_version_id = fields.Many2one(
        MODEL_LABORATORY_FILE_VERSION, string="Current Version", ondelete="restrict", readonly=True, copy=False
    )
    # Every version of the file.
    version_ids = fields.One2many(MODEL_LABORATORY_FILE_VERSION, "file_id", string="Versions")

    _folder_path_unique = models.Constraint(
        "UNIQUE(folder_id, path_key)", "The folder already has a file with this path, perhaps in another letter case."
    )
    _current_version_unique = models.Constraint(
        "UNIQUE(current_version_id)", "A version is the current version of one file only."
    )

    @api.depends("path")
    def _compute_path_key(self):
        for file in self:
            file.path_key = path_key(file.path) if file.path else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals["path"] = normal_text(vals.get("path"))
        return super().create(vals_list)

    def write(self, vals):
        if set(IDENTITY_FIELDS) & set(vals):
            raise UserError(self.env._("A file keeps its folder and its path; files are never moved or renamed."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_file(self):
        raise UserError(self.env._("Laboratory files are never deleted."))

    @api.constrains("path")
    def _check_path(self):
        for file in self:
            if not is_relative_path(file.path):
                raise ValidationError(
                    self.env._(
                        "A file's path is relative to its folder, such as HPLC/run-01.csv, never a path on a "
                        "computer: %s",
                        file.path or "",
                    )
                )
