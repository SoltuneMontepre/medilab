import posixpath

from psycopg2 import IntegrityError, errorcodes

from odoo import api, fields, models
from odoo.exceptions import ConcurrencyError, UserError, ValidationError
from odoo.tools import SQL, mute_logger

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    CONFLICT,
    EDITED_ONLINE,
    FILE_READ,
    FILE_WRITE,
    FOLDER_READ,
    FOLDER_WRITE,
    MOVE_CURRENT_CONTEXT,
    OFFICE_EXTENSIONS,
    RAW_DATA,
    RESTORED,
    SYNCED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_PERMISSION_MIXIN,
)
from odoo.addons.sol_laboratory.fields.big_integer import BigInteger
from odoo.addons.sol_laboratory.services.laboratory_paths import is_relative_path, normal_text, path_key

# A file is found by its folder and path, which never change.
IDENTITY_FIELDS = ("folder_id", "path", "path_key")
# What reading and writing a file need of its folder.
FOLDER_ACCESS = {FILE_READ: FOLDER_READ, FILE_WRITE: FOLDER_WRITE}


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
    # Number of the current version.
    current_number = fields.Integer(related="current_version_id.number", string="Current Number")
    # Size of the current version in bytes.
    current_size = BigInteger(related="current_version_id.size", string="Size")
    # The user who saved the current version.
    current_user_id = fields.Many2one(related="current_version_id.user_id", string="Saved By")

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
        if "current_version_id" in vals and not self.env.context.get(MOVE_CURRENT_CONTEXT):
            raise UserError(self.env._("A file's current version changes only by saving or restoring the file."))
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

    def _check_file_access(self, access):
        """Refuse the user what they may not do with these files: read their versions, or write a new one. Their
        folders decide, with _check_folder_access(): membership, the sample of a sample folder, and whether the folder
        is archived or turned off. Callers check it before they act with full rights; versions check their file."""
        self.sudo().folder_id.with_env(self.env)._check_folder_access(FOLDER_ACCESS[access])

    def _is_raw_data(self):
        """Raw data from instruments: the file is in a folder of a sample's raw data. A folder without a category holds
        no raw data; what applies to its files is decided by the features built on them."""
        self.ensure_one()
        return self.sudo().folder_id.category == RAW_DATA

    def _is_office_document(self):
        """A Word, Excel or PowerPoint document, whatever the letter case of its extension."""
        self.ensure_one()
        return posixpath.splitext(self.path)[1].removeprefix(".").lower() in OFFICE_EXTENSIONS

    @api.model
    def _get_or_create(self, folder, path):
        """The file of the path in the folder, created when it has none. A path that differs only in letter case or
        Unicode form is the same file. Two first saves of one path at once make one file: the second one's creation
        fails on the unique key and Odoo runs its request again, when it finds the file."""
        files = self.sudo()
        path = normal_text(path)
        file = files.search([("folder_id", "=", folder.id), ("path_key", "=", path_key(path))], limit=1)
        if file:
            return file.with_env(self.env)
        try:
            with self.env.cr.savepoint(), mute_logger("odoo.sql_db"):
                return files.create({"folder_id": folder.id, "path": path}).with_env(self.env)
        except IntegrityError as error:
            if error.pgcode != errorcodes.UNIQUE_VIOLATION:
                raise
            # Committed by a transaction this one cannot see; ConcurrencyError is what Odoo's request retrying retries.
            raise ConcurrencyError(
                self.env._("Another save created the file %s meanwhile; the save is run again.", path)
            ) from error

    def _check_can_add_version(self, user, device):
        """Refuse a new version of the files that breaks a rule every save obeys, whoever stores it and with whatever
        rights: their folder is archived or turned off. Features built on files add their rules here, such as a lock
        someone else holds. Access to the folder is the caller's to check, with _check_file_access()."""
        folders = self.sudo().folder_id
        folders._check_not_archived()
        folders._check_enabled()

    def _add_version(
        self, *, sha256, size, storage_key, source, user, device=None, base_version=None, restored_from=None
    ):
        """Store a version of the file, the one way versions are made, and return it.

        The version is numbered after the file's last one and becomes current, with a change row, unless it is made
        from a base version that is no longer current: then it is kept as a conflict and the current version stays.
        Content the current version already has adds nothing, and the current version is returned; a restore always
        adds a version, with the content of the version it restores.

        A concurrent save of the same file makes Odoo run the whole request again, so whatever the caller does before
        in the same request must be safe to run twice."""
        self.ensure_one()
        self._check_can_add_version(user, device)
        if source not in (SYNCED, EDITED_ONLINE, RESTORED) or (source == RESTORED) != bool(restored_from):
            raise ValueError("A version is synced or edited online, or restored from a version.")
        if (base_version and base_version.file_id != self) or (restored_from and restored_from.file_id != self):
            raise ValueError("A version is made from a version of the same file.")
        file = self.sudo()
        file._lock_for_new_version()
        current = file.current_version_id
        if source != RESTORED and current.sha256 == sha256:
            return current.with_env(self.env)
        if source != RESTORED and base_version and base_version != current:
            source = CONFLICT
        version = (
            self.env[MODEL_LABORATORY_FILE_VERSION]
            .sudo()
            .create(
                {
                    "file_id": file.id,
                    "number": file._last_number() + 1,
                    "parent_version_id": current.id,
                    "restored_from_id": restored_from.id if restored_from else False,
                    "source": source,
                    "size": size,
                    "sha256": sha256,
                    "storage_key": storage_key,
                    "user_id": user.id,
                    "device_id": device.id if device else False,
                }
            )
        )
        if source != CONFLICT:
            file._make_current(version)
        return version.with_env(self.env)

    def _lock_for_new_version(self):
        # Every save updates the file's row, a conflict too, so a concurrent save of the file waits for this one and
        # then fails with a serialization error, which Odoo answers by running its request again with what this one
        # stored. A lock alone would let it number its version from a snapshot without this one. Raw SQL, as the ORM
        # only takes locks that do not wait.
        self.flush_recordset()
        self.env.cr.execute(
            SQL(
                "UPDATE medilab_laboratory_file SET write_date = %s, write_uid = %s WHERE id = %s",
                fields.Datetime.now(),
                self.env.uid,
                self.id,
            )
        )
        self.invalidate_recordset(["write_date", "write_uid"])

    def _last_number(self):
        versions = self.env[MODEL_LABORATORY_FILE_VERSION].sudo()
        return versions.search([("file_id", "=", self.id)], order="number desc", limit=1).number

    def _make_current(self, version):
        """Make the version the file's current one and add the change row computers read. The current version only
        moves on to a newer version, never back to an older row."""
        current = self.current_version_id
        if version.file_id != self or (current and version.number <= current.number):
            raise UserError(self.env._("A file's current version only moves on to a newer version of the file."))
        self.with_context(**{MOVE_CURRENT_CONTEXT: True}).write({"current_version_id": version.id})
        self.env[MODEL_LABORATORY_FILE_CHANGE].sudo().create(
            {"folder_id": self.folder_id.id, "file_id": self.id, "version_id": version.id}
        )
