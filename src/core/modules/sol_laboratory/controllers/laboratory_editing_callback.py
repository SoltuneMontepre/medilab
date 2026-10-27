from odoo import http

from odoo.addons.sol_laboratory.constants.laboratory_editing import CALLBACK_ROUTE
from odoo.addons.sol_laboratory.services.laboratory_editing_callback import serve_callback


class MedilabLaboratoryEditingCallback(http.Controller):
    @http.route(
        CALLBACK_ROUTE,
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        readonly=False,
    )
    def callback(self, callback_token):
        return serve_callback(callback_token)
