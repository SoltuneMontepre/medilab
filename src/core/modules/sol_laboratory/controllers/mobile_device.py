from odoo import http

from odoo.addons.sol_laboratory.services.request_env import request_env


class MobileDeviceController(http.Controller):
    @http.route("/medilab/mobile/register", type="jsonrpc", auth="user", methods=["POST"])
    def register(self, token, platform):
        device = request_env()["medilab.mobile.device"].register_token(token, platform)
        return {"id": device.id, "active": device.active}

    @http.route("/medilab/mobile/unregister", type="jsonrpc", auth="user", methods=["POST"])
    def unregister(self, token):
        device = request_env()["medilab.mobile.device"].unregister_token(token)
        return {"id": device.id, "active": device.active}
