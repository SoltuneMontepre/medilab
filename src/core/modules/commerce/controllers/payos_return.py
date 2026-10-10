from odoo.http import Controller, request, route

from odoo.addons.commerce.constants.payos import CANCEL_ROUTE, RETURN_ROUTE

RETURN_PAGE = "commerce.payos_return_page"


# The pages PayOS sends the customer back to; they record nothing, since only PayOS's notification confirms a payment.
class PayosReturn(Controller):
    @route(RETURN_ROUTE, type="http", auth="public", methods=["GET"])
    def returned(self, **params):
        return request.render(RETURN_PAGE, {"cancelled": False})

    @route(CANCEL_ROUTE, type="http", auth="public", methods=["GET"])
    def cancelled(self, **params):
        return request.render(RETURN_PAGE, {"cancelled": True})
