from typing import Any, cast
from urllib.parse import urlsplit

from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_IR_HTTP, MODEL_RES_LANG
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

LANGUAGE_COOKIE = "frontend_lang"


class PortalLanguage(http.Controller):
    """The portal's language switcher: a signed-in user's choice is saved on their profile, so e-mails follow it."""

    @http.route("/my/language", type="http", auth="public", methods=["POST"], **FRONTEND_PAGE)
    def language(self, lang=None, redirect=None, **kwargs):
        env = request_env()
        code = env[MODEL_IR_HTTP].get_nearest_lang(lang or "")
        response = request.redirect(self._back(redirect), local=True)
        if not code:
            return response
        if not env.user._is_public():
            # Writing a user's language clears the registry cache, so an unchanged one is not written.
            if env.user.lang != code:
                env.user.write({"lang": code})
            # Pages that are not frontend pages take the language the session got at sign-in.
            request.session.context = {**(request.session.context or {}), "lang": code}
        # The frontend sets this cookie to the page's language on the future response; set there, the choice wins.
        # Odoo copies werkzeug's signature onto FutureResponse.set_cookie, which the type checker reads as unbound.
        cast("Any", request.future_response).set_cookie(LANGUAGE_COOKIE, code)
        return response

    def _back(self, redirect):
        """The local page the switch came from, without its language prefix, so the new language applies."""
        parts = urlsplit(redirect or "")
        if parts.scheme or parts.netloc or not parts.path.startswith("/"):
            return "/my"
        prefixes = {f"/{language.url_code}" for language in request_env()[MODEL_RES_LANG]._get_frontend().values()}
        path = parts.path
        head, _, rest = path[1:].partition("/")
        if f"/{head}" in prefixes:
            path = f"/{rest}"
        return f"{path}?{parts.query}" if parts.query else path
