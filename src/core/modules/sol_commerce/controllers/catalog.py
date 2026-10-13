from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import SOURCE_PORTAL, STATUS_DRAFT
from odoo.addons.sol_commerce.constants.xml_ids import PUBLIC_PARTNER
from odoo.addons.sol_laboratory.services.request_env import request_env

CART_SESSION = "medilab_cart_id"


class Catalog(http.Controller):
    @http.route("/catalog", type="http", auth="public")
    def catalog(self, sample_type=None, group=None, name=None, price_min=None, price_max=None, **kwargs):
        products = request_env()[MODEL_PRODUCT_TEMPLATE]
        sample_types = products.catalog_filters()["sample_types"]
        groups = products.catalog_filters()["groups"]
        sample = self._record(sample_types, sample_type)
        parameter_group = self._record(groups, group)
        found = products.sudo().search(
            products._catalog_domain(sample, parameter_group, name, price_min, price_max),
            order="name",
        )
        return request.render(
            "sol_commerce.catalog_page",
            {
                "groups": self._groups(found.filtered("parameter_id")),
                "packages": found.filtered("service_package_id"),
                "sample_types": sample_types,
                "parameter_groups": groups,
                "sample_type": sample_type or "",
                "group": group or "",
                "name": name or "",
                "price_min": price_min or "",
                "price_max": price_max or "",
                "cart_quantity": sum(self._cart()._catalog_lines().mapped("product_uom_qty")),
            },
        )

    @http.route("/catalog/add", type="http", auth="public", methods=["POST"])
    def add(self, product_tmpl_id, quantity="1", **kwargs):
        product = request_env()[MODEL_PRODUCT_TEMPLATE].sudo().browse(int(product_tmpl_id)).exists()
        try:
            self._get_or_create_cart().add_catalog_product(product, self._quantity(quantity))
        except UserError as error:
            return request.redirect(f"/catalog?error={quote(str(error))}")
        return request.redirect("/cart")

    @http.route("/cart", type="http", auth="public")
    def cart(self, error=None, message=None, **kwargs):
        order = self._cart()
        return request.render(
            "sol_commerce.cart_page",
            {
                "order": order,
                "lines": order._catalog_lines(),
                "error": error,
                "message": message,
                "public": request_env().user._is_public(),
            },
        )

    @http.route("/cart/line", type="http", auth="public", methods=["POST"])
    def update_line(self, line_id, quantity="1", **kwargs):
        order = self._cart()
        line = order._catalog_lines().filtered(lambda item: item.id == int(line_id))[:1]
        if not line:
            return request.redirect("/cart")
        qty = self._quantity(quantity, allow_zero=True)
        if qty == 0:
            line.sudo().unlink()
        else:
            line.sudo().product_uom_qty = qty
            line._lock_catalog_price()
        return request.redirect("/cart")

    @http.route("/cart/save", type="http", auth="public", methods=["POST"])
    def save(self, **kwargs):
        if not self._cart():
            return request.redirect("/catalog")
        return request.redirect("/cart?message=Saved")

    @http.route("/cart/submit", type="http", auth="public", methods=["POST"])
    def submit(self, name=None, email=None, phone=None, **kwargs):
        order = self._get_or_create_cart()
        try:
            order.action_submit({"name": name, "email": email, "phone": phone})
        except UserError as error:
            return request.redirect(f"/cart?error={quote(str(error))}")
        request.session.pop(CART_SESSION, None)
        return request.render("sol_commerce.order_submitted", {"order": order.sudo()})

    def _groups(self, products):
        grouped = []
        for product in products.sorted(lambda item: (item.parameter_id.main_group_id.name or "", item.name or "")):
            group = product.parameter_id.main_group_id
            if grouped and grouped[-1][0] == group:
                grouped[-1][1] |= product
            else:
                grouped.append([group, product])
        return grouped

    def _cart(self):
        order = request_env()[MODEL_SALE_ORDER].sudo().browse(request.session.get(CART_SESSION)).exists()
        user = request_env().user
        if order and order.order_status == STATUS_DRAFT and order.source == SOURCE_PORTAL:
            if user._is_public() or order._owned_by(user):
                return order
        if not user._is_public():
            commercial = user.partner_id.commercial_partner_id
            existing = (
                request_env()[MODEL_SALE_ORDER]
                .sudo()
                .search(
                    [
                        ("order_status", "=", STATUS_DRAFT),
                        ("source", "=", SOURCE_PORTAL),
                        "|",
                        ("customer_id", "child_of", commercial.id),
                        ("partner_id", "child_of", commercial.id),
                    ],
                    limit=1,
                    order="id desc",
                )
            )
            if existing:
                request.session[CART_SESSION] = existing.id
                return existing
        return request_env()[MODEL_SALE_ORDER].sudo()

    def _get_or_create_cart(self):
        order = self._cart()
        if order:
            return order
        user = request_env().user
        if user._is_public():
            partner = request_env().ref(PUBLIC_PARTNER)
            customer_id = False
        else:
            partner = user.partner_id
            customer_id = partner.commercial_partner_id.id
        order = (
            request_env()[MODEL_SALE_ORDER]
            .sudo()
            .create(
                {
                    "partner_id": partner.id,
                    "customer_id": customer_id,
                    "source": SOURCE_PORTAL,
                    "order_status": STATUS_DRAFT,
                    "user_id": False,
                }
            )
        )
        request.session[CART_SESSION] = order.id
        return order

    def _record(self, records, value):
        if not value:
            return records.browse()
        try:
            record_id = int(value)
        except ValueError:
            return records.browse()
        return records.browse(record_id).exists()

    def _quantity(self, value, allow_zero=False):
        try:
            quantity = float(value)
        except (TypeError, ValueError) as error:
            raise UserError(request_env()._("A catalog line needs a quantity of at least 1.")) from error
        if quantity == 0 and allow_zero:
            return 0
        if quantity < 1:
            raise UserError(request_env()._("A catalog line needs a quantity of at least 1."))
        return quantity
