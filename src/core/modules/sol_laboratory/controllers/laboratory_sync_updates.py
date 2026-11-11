from odoo import http

from odoo.addons.sol_laboratory.constants.sync_updates import METHODS, UPDATE_PREFIX
from odoo.addons.sol_laboratory.services.sync_update_http import update


class LaboratorySyncUpdates(http.Controller):
    @http.route(
        UPDATE_PREFIX + "/<string:target>/<string:arch>/<string:version>",
        type="http",
        auth="none",
        methods=METHODS,
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def updates(self, target, arch, version, **_parameters):
        return update(target, arch, version)
