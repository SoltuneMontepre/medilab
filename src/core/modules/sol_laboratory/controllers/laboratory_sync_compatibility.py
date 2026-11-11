import os
import re

from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.sync_updates import LEGACY_MODE_VARIABLE, LEGACY_PREFIX
from odoo.addons.sol_laboratory.services.sync_update_http import legacy_refusal, update


class LaboratorySyncCompatibility(http.Controller):
    @http.route(
        [LEGACY_PREFIX, LEGACY_PREFIX + "/", LEGACY_PREFIX + "/<path:legacy_path>"],
        type="http",
        auth="none",
        csrf=False,
        save_session=False,
        readonly=True,
    )
    def legacy(self, legacy_path="", **_parameters):
        match = re.fullmatch(r"updates/([^/]+)/([^/]+)/([^/]+)", legacy_path)
        if (
            match
            and request.httprequest.method in ("GET", "HEAD")
            and os.environ.get(LEGACY_MODE_VARIABLE) == "manifest"
        ):
            return update(*match.groups(), trust="legacy")
        return legacy_refusal()
