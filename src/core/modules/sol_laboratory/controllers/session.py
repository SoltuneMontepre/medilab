from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY
from odoo.addons.web.controllers.session import Session


def _readonly_unless_signed_in(controller, rule, args):
    # Signing out writes an audit entry, which needs a read/write cursor.
    return not request.session.uid


class MedilabSession(Session):
    @http.route(readonly=_readonly_unless_signed_in)
    def destroy(self):
        self._log_logout()
        return super().destroy()

    @http.route(readonly=_readonly_unless_signed_in)
    def logout(self, redirect="/odoo"):
        self._log_logout()
        return super().logout(redirect)

    def _log_logout(self):
        # The session still names its user here; once it ends, only the public user is left.
        if request.session.uid:
            request.env[MODEL_AUDIT_ENTRY].with_user(request.session.uid)._log_session("logout")
