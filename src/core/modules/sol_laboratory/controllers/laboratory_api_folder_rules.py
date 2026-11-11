from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import FOLDER_READ, FOLDER_SHARE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route


def rule_values(rule):
    return {
        "id": rule.id,
        "kind": rule.kind,
        "pattern": rule.pattern,
        "recursive": rule.recursive,
        "enabled": rule.enabled,
    }


class LaboratoryApiFolderRules(http.Controller):
    """The sync rules of a folder, which say which files of a bound folder on a computer are synced. Its members read
    them; its owner and administrators change them."""

    @laboratory_api_route("/folders/<int:folder_id>/rules", ["GET"], "listFolderRules")
    def list_rules(self, device, _body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_READ)
        return {"rules": [rule_values(rule) for rule in folder.sudo().rule_ids]}

    @laboratory_api_route("/folders/<int:folder_id>/rules", ["POST"], "addFolderRule")
    def add_rule(self, device, body, folder_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        rule = folder._add_rule(body["kind"], body["pattern"], body.get("recursive", True))
        return {"rule": rule_values(rule)}

    @laboratory_api_route("/folders/<int:folder_id>/rules/<int:rule_id>", ["PATCH"], "changeFolderRule")
    def change_rule(self, device, body, folder_id, rule_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        return {"rule": rule_values(folder._change_rule(rule_id, body))}

    @laboratory_api_route("/folders/<int:folder_id>/rules/<int:rule_id>", ["DELETE"], "removeFolderRule")
    def remove_rule(self, device, _body, folder_id, rule_id):
        folder = device.env[MODEL_LABORATORY_FOLDER]._checked_for(folder_id, FOLDER_SHARE)
        # A rule already removed is gone, as a repeated removal finds it.
        folder.sudo().rule_ids.filtered(lambda row: row.id == rule_id).unlink()
