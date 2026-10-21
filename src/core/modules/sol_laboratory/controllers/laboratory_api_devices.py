from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_files import NOT_FOUND
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


class LaboratoryApiDevices(http.Controller):
    """The person's signed-in computers. Administrators revoke other people's computers in the back office."""

    @laboratory_api_route("/devices", ["GET"], "listDevices")
    def list_devices(self, device, _body):
        devices = device.search([("user_id", "=", device.env.uid)])
        return {"devices": [each._laboratory_api_values(device) for each in devices]}

    @laboratory_api_route("/devices/<int:device_id>/revoke", ["POST"], "revokeDevice", permission=False)
    def revoke_device(self, device, _body, device_id):
        # A person who lost the laboratory files permission still revokes their own computers, so they are found and
        # revoked with full rights among the person's own.
        target = device.sudo().search([("id", "=", device_id), ("user_id", "=", device.env.uid)])
        if not target:
            raise LaboratoryFileError(NOT_FOUND, device.env._("This computer does not exist or is not one of yours."))
        target.action_revoke()
        return {"device": target._laboratory_api_values(device)}
