from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.laboratory_files import OWNER_ROLE, TWO_WAY, UPLOAD_ONLY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
    MODEL_SAMPLE,
)


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
        [("raw", "Raw Data"), ("working", "Working Documents"), ("result", "Results"), ("report", "Reports")]
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

    _owner_root_unique = models.Constraint(
        "UNIQUE(owner_id, root)", "The owner already has a folder with this name; choose another name."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault("root", vals.get("name"))
        folders = super().create(vals_list)
        folders._add_owner_rows()
        return folders

    def write(self, vals):
        if "root" in vals and any(folder.root != vals["root"] for folder in self):
            raise UserError(self.env._("The name a folder was created with never changes; rename the folder instead."))
        return super().write(vals)

    def _add_owner_rows(self):
        # The owner reads and writes the folder as every member does, through their own row.
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER].sudo()
        for folder in self.sudo():
            row = folder.member_ids.filtered(lambda member, folder=folder: member.user_id == folder.owner_id)
            if row:
                row.role = OWNER_ROLE
            else:
                members.create({"folder_id": folder.id, "user_id": folder.owner_id.id, "role": OWNER_ROLE})
