import base64
from urllib.parse import quote

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER
from odoo.addons.sol_laboratory.constants.routes import FRONTEND_PAGE
from odoo.addons.sol_laboratory.services.request_env import request_env


class CustomerAccount(CustomerPortal):
    """The customer's profile on Odoo's account page: identity, logo, order history and the people of a business."""

    def _prepare_my_account_rendering_values(self, *args, **kwargs):
        values = super()._prepare_my_account_rendering_values(*args, **kwargs)
        customer = self._customer()
        values["medilab_customer"] = customer
        values["customer_orders"] = (
            request_env()[MODEL_SALE_ORDER]._portal_orders(request_env().user) if customer else []
        )
        return values

    def _prepare_address_form_values(self, partner_sudo, *args, **kwargs):
        values = super()._prepare_address_form_values(partner_sudo, *args, **kwargs)
        if values["current_partner"].commercial_partner_id.vat and not values["vat_warning"]:
            values["vat_warning"] = request_env()._("Your tax code is registered. Contact the laboratory to change it.")
        return values

    def _validate_address_values(self, address_values, partner_sudo, *args, **kwargs):
        invalid_fields, missing_fields, error_messages = super()._validate_address_values(
            address_values, partner_sudo, *args, **kwargs
        )
        registered = partner_sudo.commercial_partner_id.vat
        if registered and address_values.get("vat", registered) != registered:
            invalid_fields.add("vat")
            error_messages.append(request_env()._("Your tax code is registered. Contact the laboratory to change it."))
        return invalid_fields, missing_fields, error_messages

    @http.route("/my/identity", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def identity(self, citizen_id=None, **kwargs):
        return self._run(lambda customer: customer.set_citizen_id(citizen_id), "/my/account")

    @http.route("/my/logo", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def logo(self, logo=None, **kwargs):
        data = logo.read() if logo else b""
        if not data:
            return request.redirect(f"/my/account?error={quote(request_env()._('Choose a logo to upload.'))}")
        return self._run(
            lambda customer: customer.write({"image_1920": base64.b64encode(data).decode()}), "/my/account"
        )

    @http.route("/my/logo/remove", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def remove_logo(self, **kwargs):
        return self._run(lambda customer: customer.write({"image_1920": False}), "/my/account")

    @http.route("/my/contacts", type="http", auth="user", **FRONTEND_PAGE)
    def contacts(self, error=None, **kwargs):
        customer = self._business()
        if not customer:
            return request.redirect("/my/account")
        return request.render(
            "sol_commerce.contact_list", {"customer": customer, "contacts": customer._contacts(), "error": error}
        )

    @http.route(["/my/contacts/new", "/my/contacts/<int:contact_id>"], type="http", auth="user", **FRONTEND_PAGE)
    def contact(self, contact_id=None, error=None, **kwargs):
        customer = self._business()
        if not customer:
            return request.redirect("/my/account")
        contact = self._contact(customer, contact_id) if contact_id else request_env()["res.partner"]
        if contact_id and not contact:
            return request.redirect("/my/contacts")
        return request.render("sol_commerce.contact_form", {"contact": contact, "error": error})

    @http.route("/my/contacts/save", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def save_contact(self, contact_id=None, **form):
        customer = self._business()
        if not customer:
            return request.redirect("/my/account")
        contact = self._contact(customer, int(contact_id)) if contact_id else None
        try:
            customer.save_contact(form, contact)
        except (AccessError, UserError) as error:
            back = f"/my/contacts/{contact_id}" if contact_id else "/my/contacts/new"
            return request.redirect(f"{back}?error={quote(str(error))}")
        return request.redirect("/my/contacts")

    @http.route("/my/contacts/<int:contact_id>/remove", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def remove_contact(self, contact_id, **kwargs):
        return self._run_on_contact(contact_id, lambda customer, contact: customer.remove_contact(contact))

    @http.route("/my/contacts/<int:contact_id>/default", type="http", auth="user", methods=["POST"], **FRONTEND_PAGE)
    def default_contact(self, contact_id, **kwargs):
        return self._run_on_contact(contact_id, lambda customer, contact: customer.set_default_contact(contact))

    def _customer(self):
        return request_env()[MODEL_CUSTOMER]._of_user(request_env().user)

    def _business(self):
        customer = self._customer()
        return customer if customer.is_company else customer.browse()

    def _contact(self, customer, contact_id):
        return customer._contacts().filtered(lambda partner: partner.id == contact_id)

    def _run(self, action, back):
        customer = self._customer()
        if not customer:
            return request.redirect("/my")
        try:
            action(customer)
        except (AccessError, UserError) as error:
            return request.redirect(f"{back}?error={quote(str(error))}")
        return request.redirect(back)

    def _run_on_contact(self, contact_id, action):
        customer = self._business()
        contact = self._contact(customer, contact_id) if customer else None
        if not contact:
            return request.redirect("/my/contacts")
        try:
            action(customer, contact)
        except (AccessError, UserError) as error:
            return request.redirect(f"/my/contacts?error={quote(str(error))}")
        return request.redirect("/my/contacts")
