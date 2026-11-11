from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_READ, FOLDER_SHARE, INVALID_REQUEST, OWNER_ROLE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


def member_values(member):
    return {"id": member.id, "user": {"id": member.user_id.id, "name": member.user_id.name}, "role": member.role}


class LaboratoryApiFolderMembers(http.Controller):
    """The members of a folder. Its members read them; its owner and administrators add and remove them."""

    @laboratory_api_route("/folders/<int:folder_id>/members", ["GET"], "listFolderMembers")
    def list_members(self, device, _body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)
        return {"members": [member_values(member) for member in folder.sudo().member_ids]}

    @laboratory_api_route("/folders/<int:folder_id>/members", ["POST"], "addFolderMember")
    def add_member(self, device, body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        return {"member": member_values(folder._add_member(body["user_id"]))}

    @laboratory_api_route("/folders/<int:folder_id>/members/<int:member_id>", ["DELETE"], "removeFolderMember")
    def remove_member(self, device, _body, folder_id, member_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        # A member already removed is gone, as a repeated removal finds it.
        member = folder.sudo().member_ids.filtered(lambda row: row.id == member_id)
        if member.role == OWNER_ROLE:
            raise LaboratoryFileError(
                INVALID_REQUEST,
                device.env._("The owner of a folder cannot be removed from it; an administrator changes its owner."),
            )
        member.unlink()

    @laboratory_api_route("/folders/<int:folder_id>/member-candidates", ["GET"], "searchFolderMemberCandidates")
    def search_candidates(self, device, _body, folder_id, q):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        users = folder._member_candidates(q)
        return {"candidates": [{"id": user.id, "name": user.name, "login": user.login} for user in users]}
