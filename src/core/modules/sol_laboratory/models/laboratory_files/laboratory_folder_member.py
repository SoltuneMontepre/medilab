from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, NOT_ELIGIBLE, OWNER_ROLE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


# Links a folder to a person who can read and write it.
class LaboratoryFolderMember(models.Model):
    _name = MODEL_LABORATORY_FOLDER_MEMBER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Folder Member"
    _order = "folder_id, role desc, id"
    _rec_name = "user_id"
    # Members are added and removed; a role changes only with the folder's owner.
    _permission_actions = ("read", "create", "delete")

    # The folder.
    folder_id = fields.Many2one(MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="cascade")
    # The member.
    user_id = fields.Many2one(MODEL_RES_USERS, string="Member", required=True, ondelete="cascade")
    # owner or member; the owner's row cannot be removed.
    role = fields.Selection([(OWNER_ROLE, "Owner"), (MEMBER_ROLE, "Member")], required=True, default=MEMBER_ROLE)

    _folder_user_unique = models.Constraint(
        "UNIQUE(folder_id, user_id)", "This person is already a member of the folder."
    )
    _folder_owner_unique = models.UniqueIndex(
        f"(folder_id) WHERE role = '{OWNER_ROLE}'", "A folder has one owner; change the folder's owner instead."
    )

    @api.model_create_multi
    def create(self, vals_list):
        folders = self.env[MODEL_LABORATORY_FOLDER].browse(
            {vals["folder_id"] for vals in vals_list if vals.get("folder_id")}
        )
        folders._check_not_archived()
        # The owner's row comes with the folder, which checks its owner; anyone else must be able to use laboratory files.
        self._check_eligible(
            {vals["user_id"] for vals in vals_list if vals.get("user_id") and vals.get("role") != OWNER_ROLE}
        )
        return super().create(vals_list)

    def write(self, vals):
        # The members of an archived folder do not change; they are only removed, so access can always be withdrawn.
        self.folder_id._check_not_archived()
        return super().write(vals)

    @api.model
    def _check_eligible(self, user_ids):
        """Refuse anyone who cannot be a member: only active internal users with the laboratory files permission are."""
        users = self.env[MODEL_RES_USERS].sudo()
        if user_ids and users.search_count(Domain("id", "in", list(user_ids)) & self._eligible_domain()) < len(
            user_ids
        ):
            # One message whatever the reason, so it does not tell who has an account or which permission.
            raise LaboratoryFileError(NOT_ELIGIBLE, self.env._("This person cannot be added to the folder."))

    @api.model
    def _eligible_domain(self):
        """The people who can be added to a folder: active internal users with the laboratory files permission."""
        return (
            Domain("active", "=", True)
            & Domain("share", "=", False)
            & Domain("all_group_ids", "in", self.env.ref(LABORATORY_FILES_GROUP).ids)
        )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_owner(self):
        if any(member.role == OWNER_ROLE for member in self):
            raise UserError(self.env._("The owner of a folder cannot be removed from it."))
