from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_PARTNER
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env


class EmailConfirmation(http.Controller):
    @http.route(
        "/medilab/email/confirm/<string:token>", type="http", auth="public", methods=["GET"], **FRONTEND_PAGE
    )
    def confirm(self, token):
        partner = request_env()[MODEL_RES_PARTNER]._confirm_email_address(token)
        message = (
            request_env()._("Email address confirmed. Email delivery has resumed.")
            if partner
            else request_env()._("This email confirmation link is invalid or has already been used.")
        )
        return request.make_response(f"<!doctype html><html><body><p>{message}</p></body></html>")
