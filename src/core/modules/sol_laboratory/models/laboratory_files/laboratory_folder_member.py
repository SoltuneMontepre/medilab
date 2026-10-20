from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, OWNER_ROLE
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_USERS,
)


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

    @api.ondelete(at_uninstall=False)
    def _unlink_except_owner(self):
        if any(member.role == OWNER_ROLE for member in self):
            raise UserError(self.env._("The owner of a folder cannot be removed from it."))
