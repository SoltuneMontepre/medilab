from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.controllers.catalog import CART_SESSION


class CustomerOrder(http.Controller):
    @http.route("/orders", type="http", auth="user", website=False)
    def orders(self, **kwargs):
        user = request.env.user
        commercial = user.partner_id.commercial_partner_id
        orders = (
            request.env[MODEL_SALE_ORDER]
            .sudo()
            .search(
                [
                    "|",
                    ("customer_id", "child_of", commercial.id),
                    ("partner_id", "child_of", commercial.id),
                ],
                order="id desc",
            )
        )
        return request.render("sol_commerce.order_list", {"orders": orders})

    @http.route("/orders/<int:order_id>", type="http", auth="user", website=False)
    def order(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        return request.render(
            "sol_commerce.order_page",
            {"order": order, "lines": order._catalog_lines(), "requests": order.cancellation_request_ids},
        )

    @http.route("/orders/<int:order_id>/cancel", type="http", auth="user", methods=["POST"], website=False)
    def cancel(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_customer_cancel()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route("/orders/<int:order_id>/reorder", type="http", auth="user", methods=["POST"], website=False)
    def reorder(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        new = order.action_reorder()
        request.session[CART_SESSION] = new.id
        return request.redirect(f"/orders/{new.id}")

    @http.route("/orders/<int:order_id>/cancellation", type="http", auth="user", methods=["POST"], website=False)
    def cancellation(self, order_id, reason=None, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_request_cancellation(reason)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route(
        "/orders/<int:order_id>/cancellation/withdraw", type="http", auth="user", methods=["POST"], website=False
    )
    def withdraw(self, order_id, **kwargs):
        order = self._order(order_id)
        request_ = order.open_cancellation_request() if order else None
        if not request_:
            return request.not_found()
        try:
            request_.action_withdraw()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    def _order(self, order_id):
        order = request.env[MODEL_SALE_ORDER].sudo().browse(order_id).exists()
        if not order or not order._owned_by(request.env.user):
            return request.env[MODEL_SALE_ORDER]
        return order
