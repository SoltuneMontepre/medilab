from urllib.parse import quote

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.sol_commerce.constants.models import MODEL_PRODUCT_TEMPLATE, MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import SOURCE_PORTAL, STATUS_DRAFT
from odoo.addons.sol_commerce.constants.xml_ids import PUBLIC_PARTNER
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_TEST_PARAMETER
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env

CART_SESSION = "medilab_cart_id"
CART_DETAILS_SESSION = "medilab_cart_details"
CART_PATH = "/cart"
CATALOG_PATH = "/catalog"
ORDERS_PATH = "/orders"
DETAILS_PATH = "/cart/details"


class Catalog(http.Controller):
    @http.route("/catalog", type="http", auth="public", **FRONTEND_PAGE)
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
                "cart_quantity": int(sum(self._cart()._catalog_lines().mapped("product_uom_qty"))),
            },
        )

    @http.route("/catalog/packages/<int:product_tmpl_id>", type="http", auth="public", **FRONTEND_PAGE)
    def package(self, product_tmpl_id, **kwargs):
        product = request_env()[MODEL_PRODUCT_TEMPLATE].sudo().browse(product_tmpl_id).exists()
        if not product.sale_ok or not product.service_package_id:
            return request.redirect(CATALOG_PATH)
        return request.render(
            "sol_commerce.catalog_package_page",
            {
                "product": product,
                "offer": product._catalog_offer(),
                "extras": product._package_extras(),
                "cart_quantity": int(sum(self._cart()._catalog_lines().mapped("product_uom_qty"))),
            },
        )

    @http.route("/catalog/add", type="http", auth="public", methods=["POST"])
    def add(self, product_tmpl_id, quantity="1", buy_now=None, **kwargs):
        product = request_env()[MODEL_PRODUCT_TEMPLATE].sudo().browse(int(product_tmpl_id)).exists()
        chosen = request.httprequest.form.getlist("parameter_ids")
        parameters = (
            request_env()[MODEL_TEST_PARAMETER].sudo().browse([int(value) for value in chosen if value.isdigit()])
            if product.service_package_id and "parameters_chosen" in kwargs
            else None
        )
        try:
            self._get_or_create_cart().add_catalog_product(product, self._quantity(quantity), parameters)
        except UserError as error:
            back = f"{CATALOG_PATH}/packages/{product.id}" if parameters is not None else CATALOG_PATH
            return request.redirect(f"{back}?error={quote(str(error))}")
        if parameters is not None and not buy_now:
            return request.redirect(f"{CATALOG_PATH}/packages/{product.id}?added=1")
        return request.redirect(CART_PATH)

    @http.route(CART_PATH, type="http", auth="public", **FRONTEND_PAGE)
    def cart(self, error=None, **kwargs):
        order = self._cart()
        return request.render(
            "sol_commerce.cart_page",
            {
                "order": order,
                "lines": order._catalog_lines(),
                "error": error,
            },
        )

    @http.route("/cart/line", type="http", auth="public", methods=["POST"])
    def update_line(self, line_id, quantity="1", **kwargs):
        order = self._cart()
        line = order._catalog_lines().filtered(lambda item: bool(item.id == int(line_id)))[:1]
        if not line:
            return request.redirect(CART_PATH)
        try:
            qty = self._quantity(quantity, allow_zero=True)
        except UserError as error:
            return request.redirect(f"{CART_PATH}?error={quote(str(error))}")
        if qty == 0:
            line.sudo().unlink()
        else:
            line.sudo().product_uom_qty = qty
            line._lock_catalog_price()
        return request.redirect(CART_PATH)

    @http.route("/cart/save", type="http", auth="public", methods=["POST"])
    def save(self, requested_date=None, **kwargs):
        order = self._cart()
        if not order:
            return request.redirect("/catalog")
        try:
            order._set_portal_dates(requested_date)
        except UserError as error:
            return request.redirect(self._cart_error(error, requested_date))
        return request.redirect(f"{ORDERS_PATH}?saved=1")

    @http.route("/cart/check", type="http", auth="public", methods=["POST"])
    def check(self, requested_date=None, **kwargs):
        """Keep the date the customer wants the results, then ask for the order's details."""
        order = self._cart()
        if not order:
            return request.redirect(CATALOG_PATH)
        try:
            order._set_portal_dates(requested_date)
        except UserError as error:
            return request.redirect(self._cart_error(error, requested_date))
        return request.redirect(DETAILS_PATH)

    @http.route(DETAILS_PATH, type="http", auth="public", methods=["GET"], **FRONTEND_PAGE)
    def details(self, error=None, **kwargs):
        """The order's contact and sample collection, filled with what the customer chose before, beside the order."""
        order = self._cart()
        if not order._catalog_lines():
            return request.redirect(CART_PATH)
        order._prefill_collection()
        dated = order.sudo()
        contacts = order._contact_choices()
        stored = request.session.get(CART_DETAILS_SESSION) or {}
        return request.render(
            "sol_commerce.cart_details_page",
            {
                "order": dated,
                "lines": dated._catalog_lines(),
                "error": error,
                "public": request_env().user._is_public(),
                "visitor": stored.get("visitor", {}) if stored.get("order_id") == order.id else {},
                "contacts": contacts,
                "chosen_contact": (dated.partner_id & contacts) or dated.partner_id,
                "collection_days": dated._collection_days(),
            },
        )

    @http.route(f"{DETAILS_PATH}/save", type="http", auth="public", methods=["POST"])
    def save_details(self, **values):
        """Keep the details as the customer gives them, so they stay when the customer leaves and comes back."""
        order = self._cart()
        if not order:
            return request.make_response("", status=404)
        self._keep_details(order, values)
        return request.make_response("", status=204)

    @http.route("/cart/submit", type="http", auth="public", methods=["POST"])
    def submit(self, **values):
        order = self._cart()
        if not order._catalog_lines():
            return request.redirect(CART_PATH)
        visitor = self._keep_details(order, values)
        try:
            order._check_portal_collection()
            order.action_submit(visitor)
        except UserError as error:
            return request.redirect(f"{DETAILS_PATH}?error={quote(str(error))}")
        request.session.pop(CART_SESSION, None)
        request.session.pop(CART_DETAILS_SESSION, None)
        return request.render("sol_commerce.order_submitted", {"order": order.sudo()})

    def _keep_details(self, order, values):
        """Keep the contact and the collection on the order, and a visitor's own details in the session."""
        contact_id = values.get("contact_id")
        if contact_id and contact_id.isdigit():
            try:
                order.set_portal_contact(int(contact_id))
            except UserError:
                pass
        order._save_portal_collection(values)
        visitor = {key: (values.get(key) or "").strip() for key in ("name", "email", "phone")}
        if request_env().user._is_public():
            stored = request.session.get(CART_DETAILS_SESSION) or {}
            kept = stored.get("visitor", {}) if stored.get("order_id") == order.id else {}
            visitor = {key: value or kept.get(key, "") for key, value in visitor.items()}
            request.session[CART_DETAILS_SESSION] = {"order_id": order.id, "visitor": visitor}
        return visitor

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
        order = request_env()[MODEL_SALE_ORDER].sudo().browse(request.session.get(CART_SESSION) or []).exists()
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
            customer_id = user.partner_id.commercial_partner_id.id
            # A business's order starts with its default contact, which the customer can change in the cart.
            partner = request_env()[MODEL_CUSTOMER]._of_user(user).default_contact_id or user.partner_id
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

    def _cart_error(self, error, requested_date):
        # Back to the cart with the error, keeping the date the customer entered.
        return f"{CART_PATH}?error={quote(str(error))}&requested_date={quote(requested_date or '')}"

    def _id(self, value):
        # A posted record id, or None when the field was not posted or is not a number.
        return int(value) if value and value.isdigit() else None

    def _quantity(self, value, allow_zero=False):
        try:
            quantity = float(value)
        except (TypeError, ValueError) as error:
            raise UserError(request_env()._("A catalog line needs a quantity of at least 1.")) from error
        if quantity == 0 and allow_zero:
            return 0
        if quantity < 1:
            raise UserError(request_env()._("A catalog line needs a quantity of at least 1."))
        if not quantity.is_integer():
            raise UserError(request_env()._("A catalog line needs a whole number of tests."))
        return quantity
