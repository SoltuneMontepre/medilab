from urllib.parse import urlencode

from werkzeug.exceptions import HTTPException, MethodNotAllowed

from odoo import models
from odoo.http import request
from odoo.http.session import SessionExpiredException

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP
from odoo.addons.sol_laboratory.services.laboratory_editor_logging import install_editor_filter
from odoo.addons.sol_laboratory.services.laboratory_editor_page import EDITOR_PATH, page_headers


# Định Tuyến HTTP: retain native session logout/rotation and sanitize the editor's login return path.
class IrHttp(models.AbstractModel):
    _inherit = MODEL_IR_HTTP

    def _register_hook(self):
        result = super()._register_hook()
        install_editor_filter()
        return result

    @classmethod
    def _match(cls, path_info):
        try:
            return super()._match(path_info)
        except MethodNotAllowed as error:
            if EDITOR_PATH.fullmatch(path_info):
                error.error_response = page_headers(error.get_response())
                error.error_response.headers["Allow"] = "GET, HEAD"
            raise

    @classmethod
    def _handle_error(cls, exception):
        response = super()._handle_error(exception)
        path = request.httprequest.path
        if EDITOR_PATH.fullmatch(path):
            if isinstance(response, HTTPException):
                response = response.get_response()
            if isinstance(exception, SessionExpiredException) and response.status_code == 303:
                # Preserve identity confirmation when Odoo requests it; discard every caller-supplied query value.
                location = response.headers.get("Location", "").split("?", 1)[0]
                target = "/web/session/identity" if location == "/web/session/identity" else "/web/login"
                response.headers["Location"] = target + "?" + urlencode({"redirect": path})
            return page_headers(response)
        return response
