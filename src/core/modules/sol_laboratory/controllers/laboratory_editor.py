from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.services.laboratory_editor_page import open_editor, render_page
from odoo.addons.sol_laboratory.services.request_env import request_env


class LaboratoryEditor(http.Controller):
    @http.route(
        "/medilab/laboratory-files/<int:file_id>/edit", type="http", auth="user", methods=["GET"], readonly=False
    )
    def edit(self, file_id, **kwargs):
        if request.httprequest.method not in ("GET", "HEAD"):
            response = render_page(405, message=request_env()._("This page accepts GET requests only."))
            response.headers["Allow"] = "GET, HEAD"
            return response
        return open_editor(file_id)
