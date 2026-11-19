from odoo import http

from odoo.addons.sol_laboratory.constants.mobile_updates import RELEASE_PREFIX, UPDATES_PATH
from odoo.addons.sol_laboratory.constants.sync_updates import METHODS
from odoo.addons.sol_laboratory.services import mobile_update_http


class LaboratoryMobileUpdates(http.Controller):
    @http.route(
        RELEASE_PREFIX + "/<string:platform>/<string:runtime_version>/<string:version>",
        type="http",
        auth="none",
        methods=METHODS,
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def release(self, platform, runtime_version, version, **_parameters):
        return mobile_update_http.release(platform, runtime_version, version)

    @http.route(UPDATES_PATH, type="http", auth="none", methods=METHODS, csrf=False, save_session=False, readonly=True)
    def updates(self, **_parameters):
        return mobile_update_http.expo_update()
