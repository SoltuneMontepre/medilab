from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ADMINISTER,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    FOLDER_SHARE,
    FOLDER_WRITE,
    LOCKED,
    MEMBER_ROLE,
    NOT_FOUND,
    OWNER_ROLE,
    PERMISSION_DENIED,
    TWO_WAY,
    UPLOAD_ONLY,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_RES_USERS,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import FOLDER_ADMINISTRATION_GROUP, LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError
from odoo.addons.sol_laboratory.services.laboratory_paths import is_name


# Thư Mục Phòng Thí Nghiệm
class LaboratoryFolder(models.Model):
    _name = MODEL_LABORATORY_FOLDER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Folder"
    _order = "name, id"
    # Folders are archived, never deleted, and archiving one is editing it: it has no active field.
    _permission_actions = ("read", "create", "edit")
    _audit_children = ("member_ids", "rule_ids")

    # Name people see.
    name = fields.Char(required=True)
    # Name of the folder, unique for its owner; it is the name the folder was created with and never changes.
    root = fields.Char(required=True, readonly=True)
    # The user who owns the folder.
    owner_id = fields.Many2one(
        MODEL_RES_USERS, string="Owner", required=True, ondelete="restrict", default=lambda self: self.env.user
    )
    # The sample the folder belongs to; empty for a folder of no sample.
    sample_id = fields.Many2one(MODEL_SAMPLE, ondelete="restrict", index=True)
    # raw, working, result or report; empty for a folder of no sample.
    category = fields.Selection(
        [("raw", "Raw Data"), ("working", "Working Documents"), ("result", "Results"), ("report", "Reports")],
        string="Folder Category",
    )
    # upload_only sends local changes and never writes to the computer; two_way also downloads others' versions.
    sync_mode = fields.Selection(
        [(UPLOAD_ONLY, "Upload Only"), (TWO_WAY, "Two-Way")], required=True, default=UPLOAD_ONLY
    )
    # False when an administrator turned the folder off; uploads are refused and reading goes on.
    enabled = fields.Boolean(default=True)
    # When the folder was archived; empty while in use.
    archived_at = fields.Datetime(readonly=True)
    # Date until which an archived folder keeps its files.
    retention_until = fields.Date(readonly=True)
    # The device the folder was created from, for the audit.
    created_by_device_id = fields.Many2one(MODEL_LABORATORY_DEVICE, ondelete="set null", readonly=True)
    # People who can read and write the folder, the owner included.
    member_ids = fields.One2many(MODEL_LABORATORY_FOLDER_MEMBER, "folder_id", string="Members")
    # Which files of a bound local folder are synced.
    rule_ids = fields.One2many(MODEL_LABORATORY_SYNC_RULE, "folder_id", string="Sync Rules")
    # in_use, turned_off by an administrator, or archived for good.
    status = fields.Selection(
        [("in_use", "In Use"), ("turned_off", "Turned Off"), ("archived", "Archived")], compute="_compute_status"
    )

    _owner_root_unique = models.Constraint(
        "UNIQUE(owner_id, root)", "The owner already has a folder with this name; choose another name."
    )

    @api.model_create_multi
    def create(self, vals_list):
        administrator = self.env.su or self.env.user.has_group(FOLDER_ADMINISTRATION_GROUP)
        for vals in vals_list:
            vals.setdefault("root", vals.get("name"))
            # The laboratory files permission creates folders of one's own; a sample's folders come from the sample.
            if not administrator and (
                vals.get("owner_id", self.env.uid) != self.env.uid or vals.get("sample_id") or vals.get("category")
            ):
                raise LaboratoryFileError(
                    PERMISSION_DENIED,
                    self.env._("Only administrators create a folder for someone else or for a sample."),
                )
        self.env[MODEL_LABORATORY_FOLDER_MEMBER]._check_eligible(
            {vals.get("owner_id") or self.env.uid for vals in vals_list}
        )
        folders = super().create(vals_list)
        folders._add_owner_rows()
        return folders

    @api.depends("enabled", "archived_at")
    def _compute_status(self):
        for folder in self:
            if folder.archived_at:
                folder.status = "archived"
            elif folder.enabled:
                folder.status = "in_use"
            else:
                folder.status = "turned_off"

    def write(self, vals):
        self._check_not_archived()
        if "root" in vals and any(folder.root != vals["root"] for folder in self):
            raise UserError(self.env._("The name a folder was created with never changes; rename the folder instead."))
        if vals.get("owner_id"):
            self.env[MODEL_LABORATORY_FOLDER_MEMBER]._check_eligible({vals["owner_id"]})
        result = super().write(vals)
        if "owner_id" in vals:
            self._hand_over()
        return result

    def action_turn_off(self):
        """Turn the folders off: nobody uploads to them, and their members still read them."""
        self._check_folder_access(FOLDER_ADMINISTER)
        self.write({"enabled": False})

    def action_turn_on(self):
        self._check_folder_access(FOLDER_ADMINISTER)
        self.write({"enabled": True})

    def action_archive_folder(self):
        """Archive the folders for good: from then on they are only read, and they keep their files and versions until
        their retention date, the retention period of archived folders from today."""
        self._check_folder_access(FOLDER_ADMINISTER)
        days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("laboratory_folder_retention_days")
        self.write(
            {
                "archived_at": fields.Datetime.now(),
                "retention_until": fields.Date.context_today(self) + timedelta(days=days),
            }
        )

    def _check_not_archived(self):
        # There is no unarchiving, so an archived folder is only read; administrators still remove its members.
        if self.sudo().filtered("archived_at"):
            raise LaboratoryFileError(
                FOLDER_ARCHIVED, self.env._("This laboratory folder is archived: it is read, not changed.")
            )

    def _hand_over(self):
        """After a change of owner, the previous owner stays a member and the new owner's row becomes the owner's."""
        for folder in self.sudo():
            previous = folder.member_ids.filtered(
                lambda member, folder=folder: member.role == OWNER_ROLE and member.user_id != folder.owner_id
            )
            previous.role = MEMBER_ROLE
            # The partial unique index holds one owner row at a time, so the previous row changes first.
            previous.flush_recordset(["role"])
        self._add_owner_rows()

    @api.constrains("name", "root")
    def _check_names(self):
        for folder in self:
            if not (is_name(folder.name) and is_name(folder.root)):
                raise ValidationError(
                    self.env._(
                        "A folder is named, such as HPLC, never given a path on a computer: %s", folder.name or ""
                    )
                )

    @api.model
    def _check_laboratory_files_permission(self):
        if not self.env.user.has_group(LABORATORY_FILES_GROUP):
            raise LaboratoryFileError(PERMISSION_DENIED, self.env._("You do not have the laboratory files permission."))

    @api.model
    def _accessible_domain(self):
        """The folders the user works in: they are a member and, for a folder of a sample, they can see the sample."""
        samples = self.env[MODEL_SAMPLE].with_user(self.env.user)
        sample_domain = Domain("sample_id", "=", False)
        if samples.has_access("read"):
            sample_domain |= Domain("sample_id", "in", samples._search([]))
        return Domain("member_ids.user_id", "=", self.env.uid) & sample_domain

    def _check_folder_access(self, access):
        """Refuse the user what they may not do with these folders: read them, write their files, share them or
        administer them. The laboratory files API and the features built on folders call it, then act with full
        rights."""
        administrator = self.env.user.has_group(FOLDER_ADMINISTRATION_GROUP)
        if access == FOLDER_ADMINISTER and not administrator:
            raise LaboratoryFileError(
                PERMISSION_DENIED, self.env._("Only administrators can do this with a laboratory folder.")
            )
        if access == FOLDER_SHARE and administrator:
            self._check_not_archived()
        elif access != FOLDER_ADMINISTER:
            self._check_member_access(access)
        if access in (FOLDER_SHARE, FOLDER_ADMINISTER):
            try:
                self._check_lock()
            except UserError as error:
                raise LaboratoryFileError(LOCKED, error.args[0]) from error

    def _check_member_access(self, access):
        self._check_laboratory_files_permission()
        folders = self.sudo()
        if folders - folders.search(Domain("id", "in", self.ids) & self._accessible_domain()):
            raise LaboratoryFileError(
                NOT_FOUND, self.env._("This laboratory folder does not exist or you are not a member of it.")
            )
        if access in (FOLDER_WRITE, FOLDER_SHARE):
            self._check_not_archived()
        if access == FOLDER_WRITE and not all(folders.mapped("enabled")):
            raise LaboratoryFileError(
                FOLDER_DISABLED, self.env._("This laboratory folder is turned off: its files are read, not changed.")
            )
        if access == FOLDER_SHARE and folders.owner_id != self.env.user:
            raise LaboratoryFileError(
                PERMISSION_DENIED, self.env._("Only the owner of a laboratory folder and administrators can do this.")
            )

    def _add_owner_rows(self):
        # The owner reads and writes the folder as every member does, through their own row.
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER].sudo()
        for folder in self.sudo():
            row = folder.member_ids.filtered(lambda member, folder=folder: member.user_id == folder.owner_id)
            if row:
                row.role = OWNER_ROLE
            else:
                members.create({"folder_id": folder.id, "user_id": folder.owner_id.id, "role": OWNER_ROLE})
