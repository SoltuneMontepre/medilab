from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.services.laboratory_editor_page import EDITOR_PATH, open_editor, render_page
from odoo.addons.sol_laboratory.services.request_env import request_env


class LaboratoryEditor(http.Controller):
    @http.route(
        "/medilab/laboratory-files/<int:file_id>/edit", type="http", auth="user", methods=["GET"], readonly=False
    )
    def edit(self, file_id, **kwargs):
        if not EDITOR_PATH.fullmatch(request.httprequest.path):
            raise NotFound()
        if request.httprequest.method not in ("GET", "HEAD"):
            response = render_page(405, message=request_env()._("This page accepts GET requests only."))
            response.headers["Allow"] = "GET, HEAD"
            return response
        return open_editor(file_id)
