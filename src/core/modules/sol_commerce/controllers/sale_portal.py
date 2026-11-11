from odoo import http
from odoo.http import request

from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.controllers.catalog import ORDERS_PATH
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

ORDER_COUNTER = "medilab_order_count"


class SalePortal(CustomerPortal):
    """Odoo's order and quotation pages lead to MediLab's order history and order pages."""

    def _prepare_portal_counter_values(self, counter):
        if counter == ORDER_COUNTER:
            return MODEL_SALE_ORDER, request_env()[MODEL_SALE_ORDER]._portal_orders_domain(request_env().user), "sudo"
        return super()._prepare_portal_counter_values(counter)

    @http.route(["/my/quotes", "/my/quotes/page/<int:page>"], type="http", auth="user", **FRONTEND_PAGE)
    def portal_my_quotes(self, **kwargs):
        return request.redirect(ORDERS_PATH)

    @http.route(["/my/orders", "/my/orders/page/<int:page>"], type="http", auth="user", **FRONTEND_PAGE)
    def portal_my_orders(self, **kwargs):
        return request.redirect(ORDERS_PATH)

    @http.route(["/my/orders/<int:order_id>"], type="http", auth="public", **FRONTEND_PAGE)
    def portal_order_page(self, order_id, **kwargs):
        return request.redirect(f"{ORDERS_PATH}/{order_id}")
