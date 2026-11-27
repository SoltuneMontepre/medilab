from datetime import UTC, datetime
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT, MODEL_PAYMENT_TRANSACTION, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import PORTAL_ORDERS_PER_PAGE
from odoo.addons.sol_commerce.controllers.catalog import CART_SESSION, ORDERS_PATH
from odoo.addons.sol_commerce.controllers.portal import InvoicePortal
from odoo.addons.sol_commerce.models.orders.sale_order_customer import CUSTOMER_STATUSES
from odoo.addons.sol_laboratory.constants.notifications import VIETNAM_ZONE
from odoo.addons.sol_laboratory.services.request_env import request_env


class CustomerOrder(InvoicePortal):
    @http.route([ORDERS_PATH, f"{ORDERS_PATH}/page/<int:page>"], type="http", auth="user")
    def orders(self, page=1, saved=None, **kwargs):
        orders = request_env()[MODEL_SALE_ORDER]
        user = request_env().user
        filters = self._filters(kwargs)
        total = orders._portal_order_count(user, **filters)
        pager = portal_pager(url=ORDERS_PATH, url_args=filters, total=total, page=page, step=PORTAL_ORDERS_PER_PAGE)
        return request.render(
            "sol_commerce.order_list",
            {
                "orders": orders._portal_orders(user, limit=PORTAL_ORDERS_PER_PAGE, offset=pager["offset"], **filters),
                "pager": pager,
                "saved": bool(saved),
                "statuses": orders._fields["customer_status"]._description_selection(request_env()),
                "filters": filters,
                "filter_query": self._filter_query(filters),
                # A filter that matches nothing is told apart from a customer with no orders at all.
                "has_orders": bool(total) or bool(filters and orders._portal_order_count(user)),
            },
        )

    @http.route("/orders/<int:order_id>", type="http", auth="user")
    def order(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        filters = self._filters(kwargs)
        return request.render(
            "sol_commerce.order_page",
            {
                "order": order,
                "payment_request": order.payment_request_id,
                "lines": order._catalog_lines(),
                "requests": order.cancellation_request_ids,
                "support_requests": order.support_request_ids,
                "filters": filters,
                "orders_url": ORDERS_PATH + self._filter_query(filters),
            },
        )

    @http.route("/orders/<int:order_id>/cancel", type="http", auth="user", methods=["POST"])
    def cancel(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_customer_cancel()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route("/orders/<int:order_id>/reorder", type="http", auth="user", methods=["POST"])
    def reorder(self, order_id, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            new = order.action_reorder()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        request.session[CART_SESSION] = new.id
        return request.redirect(f"/orders/{new.id}{self._filter_query(self._filters(kwargs))}")

    @http.route("/orders/<int:order_id>/cancellation", type="http", auth="user", methods=["POST"])
    def cancellation(self, order_id, reason=None, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_request_cancellation(reason)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route("/orders/<int:order_id>/cancellation/withdraw", type="http", auth="user", methods=["POST"])
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

    @http.route("/orders/<int:order_id>/feedback", type="http", auth="user", methods=["POST"])
    def feedback(self, order_id, rating=None, comment=None, **kwargs):
        order = self._order(order_id)
        if not order:
            return request.not_found()
        try:
            order.action_give_feedback(rating, comment)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}")

    @http.route("/orders/<int:order_id>/quotation", type="http", auth="user")
    def quotation(self, order_id, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current:
            return request.not_found()
        advance = current.payment_request_ids.filtered(lambda payment_request: payment_request.kind == "advance")
        legacy_invoice = current.advance_invoice_id.filtered(lambda invoice: invoice.state == "posted")
        return request.render(
            "sol_commerce.quotation_page",
            {
                "order": order,
                "quotation": current,
                "quotations": order.quotation_ids.sorted("revision", reverse=True),
                "revising": order.state == "draft",
                "lines": order._catalog_lines(),
                "order_wide_lines": order._discount_lines() | order._priority_surcharge_lines(),
                "advance": advance,
                "payment_request": advance,
                "legacy_invoice": legacy_invoice,
                "legacy_invoice_url": legacy_invoice.get_portal_url() if legacy_invoice else False,
            },
        )

    @http.route(
        "/orders/<int:order_id>/payment-requests/<int:payment_request_id>/pay",
        type="http",
        auth="user",
        methods=["POST"],
    )
    def pay_request(self, order_id, payment_request_id, method=None, amount=None, received_at=None, reference=None):
        order = self._order(order_id)
        payment_request = order.payment_request_id if order else None
        if not payment_request or payment_request.id != payment_request_id:
            return request.not_found()
        back = f"/orders/{order.id}" + ("/quotation" if payment_request.kind == "advance" else "")
        try:
            with request_env().cr.savepoint():
                if method == "payos":
                    transaction = request_env()[MODEL_PAYMENT_TRANSACTION]._portal_start_request_payos(
                        payment_request, amount
                    )
                elif method == "bank_transfer":
                    payments = request_env()[MODEL_ACCOUNT_PAYMENT]
                    payments._portal_pay_request(
                        payment_request, amount, self._vietnam_receipt_time(received_at), reference
                    )
                else:
                    return request.not_found()
        except UserError as error:
            return request.redirect(f"{back}?error={quote(str(error))}")
        if method == "payos":
            payment_path = f"/orders/{order.id}/payment-requests/{payment_request.id}/pay"
            return self._payos_checkout_page(transaction, back, payment_path)
        return request.redirect(back)

    @staticmethod
    def _vietnam_receipt_time(value):
        if not value:
            return None
        try:
            moment = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError as error:
            raise UserError(request_env()._("Enter the date and time the money was received.")) from error
        return moment.replace(tzinfo=ZoneInfo(VIETNAM_ZONE)).astimezone(UTC).replace(tzinfo=None)

    @http.route("/orders/<int:order_id>/quotation/accept", type="http", auth="user", methods=["POST"])
    def accept_quotation(self, order_id, quotation_id=None, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current or (quotation_id and str(current.id) != quotation_id):
            return request.not_found()
        try:
            current.action_accept()
        except UserError as error:
            return request.redirect(f"/orders/{order.id}/quotation?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}/quotation")

    @http.route("/orders/<int:order_id>/quotation/decline", type="http", auth="user", methods=["POST"])
    def decline_quotation(self, order_id, reason=None, quotation_id=None, **kwargs):
        order = self._order(order_id)
        current = order._latest_quotation() if order else None
        if not current or (quotation_id and str(current.id) != quotation_id):
            return request.not_found()
        try:
            current.action_decline(reason)
        except UserError as error:
            return request.redirect(f"/orders/{order.id}/quotation?error={quote(str(error))}")
        return request.redirect(f"/orders/{order.id}/quotation")

    @http.route("/orders/<int:order_id>/quotation/<int:quotation_id>/pdf", type="http", auth="user")
    def quotation_pdf(self, order_id, quotation_id, **kwargs):
        order = self._order(order_id)
        sent = order.quotation_ids.filtered(lambda item: item.id == quotation_id) if order else None
        if not sent:
            return request.not_found()
        sent._audit("download")
        stream = request_env()["ir.binary"]._get_stream_from(sent.attachment_id, "raw", filename_field="name")
        return stream.get_response(as_attachment=True)

    @staticmethod
    def _filters(params):
        """The order history's filters among the request parameters, without the empty or unknown ones."""
        status = params.get("status") or ""
        filters = {
            "status": status if status in dict(CUSTOMER_STATUSES) else "",
            "search": (params.get("search") or "").strip(),
        }
        return {name: value for name, value in filters.items() if value}

    @staticmethod
    def _filter_query(filters):
        return f"?{urlencode(filters)}" if filters else ""

    def _order(self, order_id):
        order = request_env()[MODEL_SALE_ORDER].sudo().browse(order_id).exists()
        if not order or not order._owned_by(request_env().user):
            return request_env()[MODEL_SALE_ORDER]
        return order
