from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_DIGITAL_SIGNATURE
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.constants.signing import VERIFY_PATH
from odoo.addons.sol_laboratory.services.request_env import request_env


class MedilabVerify(http.Controller):
    """Anyone checks a PDF the laboratory digitally signed, without signing in."""

    @http.route(VERIFY_PATH, type="http", auth="public", methods=["GET"], **FRONTEND_PAGE)
    def verify_form(self, **kwargs):
        return request.render("sol_laboratory.verify_page", {"result": None})

    @http.route(VERIFY_PATH, type="http", auth="public", methods=["POST"], **FRONTEND_PAGE)
    def verify_file(self, document=None, **kwargs):
        data = document.read() if document else b""
        result = request_env()[MODEL_DIGITAL_SIGNATURE]._verify_file(data) if data else None
        return request.render("sol_laboratory.verify_page", {"result": result})
