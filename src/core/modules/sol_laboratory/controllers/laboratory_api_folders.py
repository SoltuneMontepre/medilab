from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_READ, FOLDER_SHARE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route


class LaboratoryApiFolders(http.Controller):
    """The folders a person works in: those they are members of and, for a folder of a sample, whose sample they see.
    Changing a folder's owner, turning it off and archiving it are done in the back office only."""

    @laboratory_api_route("/folders", ["GET"], "listFolders")
    def list_folders(self, device, _body):
        folders = device.env[MODEL_LABORATORY_FOLDER]
        found = folders.sudo().search(folders._accessible_domain()).with_env(device.env)
        return {"folders": [folder._laboratory_api_values() for folder in found]}

    @laboratory_api_route("/folders", ["POST"], "createFolder")
    def create_folder(self, device, body, idempotency_key=None):
        folder = device.env[MODEL_LABORATORY_FOLDER]._create_for_device(device, body["name"], idempotency_key)
        return {"folder": folder._laboratory_api_values()}

    @laboratory_api_route("/folders/<int:folder_id>", ["GET"], "getFolder")
    def get_folder(self, device, _body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)
        return {"folder": folder._laboratory_api_values()}

    @laboratory_api_route("/folders/<int:folder_id>", ["PATCH"], "renameFolder")
    def rename_folder(self, device, body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        folder.sudo().write({"name": body["name"]})
        return {"folder": folder._laboratory_api_values()}
