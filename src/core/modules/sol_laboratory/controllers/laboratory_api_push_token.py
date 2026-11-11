from odoo import http

from odoo.addons.sol_laboratory.constants.models import MODEL_MOBILE_DEVICE
from odoo.addons.sol_laboratory.services.laboratory_api import laboratory_api_route


class LaboratoryApiPushToken(http.Controller):
    """The Firebase token of the phone of the key. A token is registered only by a signed-in phone, never by a
    session."""

    @laboratory_api_route("/push-token", ["PUT"], "registerPushToken", permission=False)
    def register_push_token(self, device, body):
        device._check_phone()
        device.env[MODEL_MOBILE_DEVICE]._register_token(device, body["token"])

    @laboratory_api_route("/push-token", ["DELETE"], "unregisterPushToken", permission=False)
    def unregister_push_token(self, device, _body):
        device._check_phone()
        device._turn_push_token_off()
