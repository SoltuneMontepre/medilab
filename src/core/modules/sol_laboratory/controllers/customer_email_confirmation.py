from odoo import http
from odoo.http import request

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_PARTNER
from odoo.addons.sol_laboratory.constants.routes import CUSTOMER_EMAIL_CONFIRMATION_PATH, FRONTEND_PAGE


class CustomerEmailConfirmation(http.Controller):
    """Confirms the corrected address of a bounced customer contact."""

    @http.route(
        f"{CUSTOMER_EMAIL_CONFIRMATION_PATH}/<int:partner_id>",
        type="http",
        auth="public",
        methods=["GET"],
        **FRONTEND_PAGE,
    )
    def confirm_email(self, partner_id, token=None):
        if request.env is None:
            return request.not_found()
        partner = request.env[MODEL_RES_PARTNER].sudo().browse(partner_id).exists()
        confirmed = bool(partner and partner._confirm_corrected_email(token))
        return request.render("sol_laboratory.customer_email_confirmation", {"confirmed": confirmed})
