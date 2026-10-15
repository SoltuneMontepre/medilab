from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.controllers.catalog import CART_SESSION


class CustomerOrder(http.Controller):
    @http.route("/orders", type="http", auth="user", website=False)
    def orders(self, **kwargs):
        orders = request.env[MODEL_SALE_ORDER]._portal_orders(request.env.user)
        return request.render("sol_commerce.order_list", {"orders": orders})

    @http.route("/orders/<int:order_id>", type="http", auth="user", website=False)
    def order(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        return request.render(
            "sol_commerce.order_page",
            {
                "order": order,
                "lines": order._catalog_lines(),
                "requests": order.cancellation_request_ids,
                "support_requests": order.support_request_ids,
            },
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

    @http.route("/orders/<int:order_id>/feedback", type="http", auth="user", methods=["POST"], website=False)
    def feedback(self, order_id, rating=None, comment=None, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_give_feedback(rating, comment)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route("/orders/<int:order_id>/quotation", type="http", auth="user", website=False)
    def quotation(self, order_id, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current:
            return request.not_found()
        return request.render(
            "sol_commerce.quotation_page",
            {
                "order": order,
                "quotation": current,
                "quotations": order.quotation_ids.sorted("revision", reverse=True),
                "revising": order.state == "draft",
                "lines": order._catalog_lines(),
            },
        )

    @http.route("/orders/<int:order_id>/quotation/accept", type="http", auth="user", methods=["POST"], website=False)
    def accept_quotation(self, order_id, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current:
            return request.not_found()
        try:
            current.action_accept()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}/quotation?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}/quotation")

    @http.route("/orders/<int:order_id>/quotation/decline", type="http", auth="user", methods=["POST"], website=False)
    def decline_quotation(self, order_id, reason=None, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current:
            return request.not_found()
        try:
            current.action_decline(reason)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}/quotation?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}/quotation")

    @http.route("/orders/<int:order_id>/quotation/<int:quotation_id>/pdf", type="http", auth="user", website=False)
    def quotation_pdf(self, order_id, quotation_id, **kwargs):
        order = self._order(order_id)
        sent = order.quotation_ids.filtered(lambda item: item.id == quotation_id) if order else None
        if not sent:
            return request.not_found()
        sent._audit("download")
        stream = request.env["ir.binary"]._get_stream_from(sent.attachment_id, "raw", filename_field="name")
        return stream.get_response(as_attachment=True)

    def _order(self, order_id):
        order = request.env[MODEL_SALE_ORDER].sudo().browse(order_id).exists()
        if not order or not order._owned_by(request.env.user):
            return request.env[MODEL_SALE_ORDER]
        return order
