from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SUPPORT_REQUEST
from odoo.addons.sol_commerce.constants.support import SUPPORT_CLOSED
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env


class CustomerSupport(http.Controller):
    @http.route("/support", type="http", auth="user", **FRONTEND_PAGE)
    def support(self, **kwargs):
        return request.render(
            "sol_commerce.support_list", {"requests": request_env()[MODEL_SUPPORT_REQUEST].portal_requests()}
        )

    @http.route("/support/new", type="http", auth="user", **FRONTEND_PAGE)
    def new(self, order_id=None, **kwargs):
        return request.render(
            "sol_commerce.support_new",
            {
                "orders": request_env()[MODEL_SALE_ORDER]._portal_orders(request_env().user),
                "order_id": int(order_id) if order_id and order_id.isdigit() else 0,
                "subject": kwargs.get("subject", ""),
                "error": kwargs.get("error", ""),
            },
        )

    @http.route("/support/open", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def open(self, subject=None, order_id=None, body=None, **kwargs):
        files = request.httprequest.files.getlist("attachments")
        attachments = [(file.filename, file.read()) for file in files if file.filename]
        try:
            opened = request_env()[MODEL_SUPPORT_REQUEST].portal_open(subject, order_id or None, body, attachments)
        except UserError as error:
            query = f"error={quote(str(error))}&subject={quote(subject or '')}&order_id={quote(order_id or '')}"
            return request.redirect(f"/support/new?{query}")
        return request.redirect(f"/support/{opened.id}")

    @http.route("/support/<int:request_id>", type="http", auth="user", **FRONTEND_PAGE)
    def page(self, request_id, **kwargs):
        support_request = request_env()[MODEL_SUPPORT_REQUEST].portal_request(request_id)
        if not support_request:
            raise request.not_found()
        return request.render(
            "sol_commerce.support_page",
            {
                "support_request": support_request,
                "object": support_request,
                "disable_composer": support_request.status == SUPPORT_CLOSED,
            },
        )
