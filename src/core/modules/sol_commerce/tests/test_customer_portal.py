import base64
import re

from odoo.tests import HttpCase, tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

PASSWORD = "portal-customer-pass-1"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
SIGNUP = {
    "name": "Do Van Tai",
    "login": "tai@saomai.example",
    "password": "signup-pass-12",
    "confirm_password": "signup-pass-12",
    "customer_type": "business",
    "company_name": "Cong ty Sao Mai",
    "vat": "0319998887",
    "phone": "028 3999 8887",
    "street": "8 Ton Duc Thang",
    "city": "Ho Chi Minh",
}


@tagged("post_install", "-at_install")
class TestCustomerPortal(HttpCase, OrderCase):
    """Sign-up, password reset, the account page, the people of a business and the logo, through the portal."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        # A business has a tax code; Odoo counts a contact without one as a person.
        self.customer.vat = "0315678901"

    def csrf(self, url):
        match = re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text)
        if match is None:
            self.fail(f"{url} has no CSRF token.")
        return match.group(1)

    def post(self, url, data, page="/my/account", **kwargs):
        response = self.url_open(url, data={"csrf_token": self.csrf(page), **data}, allow_redirects=False, **kwargs)
        self.env.invalidate_all()
        return response

    def test_the_catalog_lists_each_parameter_with_its_add_form(self):
        html = self.url_open("/catalog").text

        self.assertIn(self.lead_product.name, html)
        self.assertRegex(html, rf'name="product_tmpl_id" value="{self.lead_product.id}"')

    def test_signing_up_registers_the_customer_who_sees_only_their_own_documents(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        self.post("/web/signup", SIGNUP, page="/web/signup")

        user = self.env["res.users"].search([("login", "=", SIGNUP["login"])])
        customer = self.env[MODEL_CUSTOMER]._of_user(user)
        self.assertEqual((customer.name, customer.default_contact_id), ("Cong ty Sao Mai", user.partner_id))
        self.authenticate(SIGNUP["login"], SIGNUP["password"])
        self.assertNotIn(order.name, self.url_open("/orders").text)
        self.assertEqual(self.url_open(f"/orders/{order.id}").status_code, 404)
        self.assertEqual(self.url_open(f"/orders/{order.id}/quotation").status_code, 404)
        invoice = self.url_open(f"/my/invoices/{order.sudo().invoice_ids[:1].id}", allow_redirects=False)
        self.assertTrue(invoice.headers["Location"].endswith("/my"))

    def test_signing_up_without_a_required_field_is_refused(self):
        response = self.post("/web/signup", dict(SIGNUP, street=""), page="/web/signup")

        self.assertIn("Fill in: Address", response.text)
        self.assertFalse(self.env["res.users"].search([("login", "=", SIGNUP["login"])]))

    def test_the_reset_page_answers_the_same_whether_or_not_the_account_exists(self):
        answers = [
            self.post("/web/reset_password", {"login": login}, page="/web/reset_password").text
            for login in ("nobody@mail.example", self.portal.login)
        ]

        for answer in answers:
            self.assertIn("Password reset instructions sent to your email address.", answer)
            self.assertNotIn("No account found", answer)

    def test_the_account_page_shows_the_customer_and_the_order_history(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")
        self.authenticate(self.portal.login, PASSWORD)

        page = self.url_open("/my/account").text

        self.assertIn(self.customer_record.code, page)
        self.assertIn(order.name, page)
        self.assertIn("Submitted", page)
        self.assertIn('href="/my/contacts"', page)
        self.assertNotIn("o_portal_profile_card", page)

    def test_a_registered_tax_code_is_not_asked_again(self):
        person = self.env["res.partner"].create(
            {
                "name": "Pham Van Long",
                "email": "long@mail.example",
                "vat": "8012345678",
                "country_id": self.env.ref("base.vn").id,
            }
        )
        self.env[MODEL_CUSTOMER].create({"partner_id": person.id, "citizen_id": "079085001234"})
        self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "login": "long",
                "password": PASSWORD,
                "partner_id": person.id,
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        self.authenticate("long", PASSWORD)

        self.assertRegex(self.url_open("/my/account").text, r'name="vat"[^>]*readonly')
        response = self.post(
            "/my/address/submit",
            {
                "partner_id": person.id,
                "name": "Pham Van Long",
                "email": "long@mail.example",
                "vat": "8019999999",
                "address_type": "billing",
                "use_delivery_as_billing": "true",
            },
        )

        self.assertIn("Your tax code is registered", response.text)
        self.assertEqual(person.vat, "8012345678")

    def test_a_business_manages_its_contacts_and_picks_one_for_an_order(self):
        self.authenticate(self.portal.login, PASSWORD)

        self.post(
            "/my/contacts/save", {"name": "Ngo Thi Lan", "function": "Accountant", "email": "lan@nuocsach.example"}
        )
        lan = self.customer_record._contacts().filtered(lambda contact: contact.name == "Ngo Thi Lan")
        self.post(f"/my/contacts/{lan.id}/default", {}, page="/my/contacts")
        self.post(
            "/my/contacts/save",
            {"contact_id": lan.id, "name": "Ngo Thi Lan", "function": "Accountant", "phone": "0909 777 888"},
        )

        self.assertEqual((lan.function, lan.phone), ("Accountant", "0909 777 888"))
        self.assertEqual(self.customer_record.default_contact_id, lan)

        self.post("/catalog/add", {"product_tmpl_id": self.lead_product.id}, page="/catalog")
        self.assertRegex(self.url_open("/cart").text, rf'<option value="{lan.id}" selected')
        self.post("/cart/submit", {"contact_id": self.contact.id}, page="/cart")
        order = self.env["sale.order"].search([("customer_id", "=", self.customer.id)], order="id desc", limit=1)
        self.assertEqual((order.order_status, order.partner_id), ("submitted", self.contact))

        self.post(f"/my/contacts/{lan.id}/remove", {}, page="/my/contacts")
        self.assertFalse(lan.active)
        self.assertFalse(self.customer_record.default_contact_id)

    def test_a_customer_uploads_a_logo_that_shows_on_new_documents_only(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        issued = bytes(order._latest_quotation().attachment_id.raw)
        self.authenticate(self.portal.login, PASSWORD)

        self.post("/my/logo", {}, files={"logo": ("logo.png", PNG, "image/png")})

        self.assertTrue(self.customer.image_128)
        self.assertIn("data:image/png;base64", self.url_open("/my/account").text)
        html = self.env["ir.actions.report"]._render_qweb_html("sale.action_report_saleorder", order.ids)[0]
        self.assertIn(b'alt="Logo"', html)
        self.assertEqual(bytes(order._latest_quotation().attachment_id.raw), issued)

        refused = self.post("/my/logo", {}, files={"logo": ("logo.gif", GIF, "image/gif")})
        self.assertIn("error=", refused.headers["Location"])

        self.post("/my/logo/remove", {})
        self.assertFalse(self.customer.image_128)

    def location(self, response):
        return response.headers["Location"]

    def test_a_customer_who_is_not_a_business_is_sent_back_to_the_account_page_from_the_contacts(self):
        self.customer.vat = False
        self.authenticate(self.portal.login, PASSWORD)

        for url in ("/my/contacts", "/my/contacts/new"):
            with self.subTest(url=url):
                self.assertTrue(self.location(self.url_open(url, allow_redirects=False)).endswith("/my/account"))
        saved = self.post("/my/contacts/save", {"name": "Ngo Thi Lan"})
        self.assertTrue(self.location(saved).endswith("/my/account"))

    def test_an_unknown_contact_sends_a_business_back_to_its_contacts(self):
        self.authenticate(self.portal.login, PASSWORD)

        unknown = self.url_open("/my/contacts/999999", allow_redirects=False)
        self.assertTrue(self.location(unknown).endswith("/my/contacts"))
        removed = self.post("/my/contacts/999999/remove", {}, page="/my/contacts")
        self.assertTrue(self.location(removed).endswith("/my/contacts"))

    def test_the_identity_form_and_an_empty_logo_answer_on_the_account_page(self):
        self.authenticate(self.portal.login, PASSWORD)

        identity = self.post("/my/identity", {"citizen_id": "079012345678"})
        self.assertIn("/my/account", self.location(identity))
        empty = self.post("/my/logo", {})
        self.assertIn("/my/account?error=", self.location(empty))

    def test_a_cart_line_is_changed_or_ignored_when_it_is_not_in_the_cart(self):
        self.authenticate(self.portal.login, PASSWORD)
        self.post("/catalog/add", {"product_tmpl_id": self.lead_product.id}, page="/catalog")
        order = self.env["sale.order"].search([("customer_id", "=", self.customer.id)], order="id desc", limit=1)
        line = order._catalog_lines()[:1]

        unknown = self.post("/cart/line", {"line_id": 0, "quantity": 2}, page="/cart")
        self.assertTrue(self.location(unknown).endswith("/cart"))
        self.assertEqual(line.product_uom_qty, 1)
        changed = self.post("/cart/line", {"line_id": line.id, "quantity": 3}, page="/cart")
        self.assertTrue(self.location(changed).endswith("/cart"))
        self.assertEqual(line.product_uom_qty, 3)
