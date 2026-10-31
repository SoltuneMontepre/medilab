from odoo import http
from odoo.http import request

from .account import ACCOUNT_PATH
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

# The cookie Odoo reads first, after the address, to choose the language of a portal page.
LANGUAGE_COOKIE = "frontend_lang"


class PortalLanguage(CustomerPortal):
    """The portal user's language, chosen on the account page and kept on their user."""

    def _prepare_my_account_rendering_values(self, *args, **kwargs):
        values = super()._prepare_my_account_rendering_values(*args, **kwargs)
        values["languages"] = request_env()["res.lang"].get_installed()
        return values

    @http.route("/my/language", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def language(self, lang=None, **kwargs):
        env = request_env()
        if lang not in dict(env["res.lang"].get_installed()):
            return request.redirect(ACCOUNT_PATH)
        env.user.lang = lang
        request.session.context["lang"] = lang
        response = request.redirect(ACCOUNT_PATH)
        response.set_cookie(LANGUAGE_COOKIE, lang)
        return response
