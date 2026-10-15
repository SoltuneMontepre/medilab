import secrets

from odoo.exceptions import UserError
from odoo.tests import tagged

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.customers import SIGNUP_CUSTOMER_KEY
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER

BUSINESS = {
    "customer_type": "business",
    "company_name": "Cong ty Thuc Pham Sao Mai",
    "vat": "0319998887",
    "phone": "028 3999 8887",
    "street": "8 Ton Duc Thang",
    "city": "Ho Chi Minh",
}
INDIVIDUAL = {
    "customer_type": "individual",
    "vat": "8019998887",
    "citizen_id": "079090009999",
    "phone": "0901 999 888",
    "street": "3 Pasteur",
    "city": "Ho Chi Minh",
}


@tagged("post_install", "-at_install")
class TestCustomerSignup(RequestCase):
    """Self-registration creates the customer, flags a matching identity and never merges it by itself."""

    def signup(self, login, details):
        values = {
            "login": login,
            "name": "Nguyen Van Binh",
            "password": secrets.token_urlsafe(),
            SIGNUP_CUSTOMER_KEY: details,
        }
        self.env["res.users"].sudo().signup(values)
        return self.env["res.users"].sudo().search([("login", "=", login)])

    def customer_of(self, user):
        return self.env[MODEL_CUSTOMER]._of_user(user)

    def test_a_business_is_the_customer_and_the_registrant_its_default_contact(self):
        user = self.signup("binh@saomai.example", BUSINESS)
        customer = self.customer_of(user)

        self.assertTrue(user.share)
        self.assertEqual(
            (customer.name, customer.vat, customer.is_company), ("Cong ty Thuc Pham Sao Mai", "0319998887", True)
        )
        self.assertEqual(user.partner_id.parent_id, customer.partner_id)
        self.assertEqual(customer.default_contact_id, user.partner_id)
        self.assertTrue(customer.code)
        self.assertFalse(customer.duplicate_of_id)

    def test_an_individual_with_a_tax_code_stays_a_person(self):
        user = self.signup("binh@mail.example", INDIVIDUAL)
        customer = self.customer_of(user)

        self.assertEqual(customer.partner_id, user.partner_id)
        self.assertEqual(customer.citizen_id, "079090009999")
        self.assertFalse(customer.is_company)
        self.assertFalse(customer.default_contact_id)

    def test_a_missing_required_field_is_refused_and_no_account_is_created(self):
        for details, field in ((dict(BUSINESS, phone=""), "Phone"), (dict(INDIVIDUAL, citizen_id=" "), "Citizen ID")):
            with self.subTest(field=field), self.assertRaisesRegex(UserError, field):
                self.signup("missing@mail.example", details)
            self.assertFalse(self.env["res.users"].sudo().search([("login", "=", "missing@mail.example")]))

    def test_a_matching_tax_code_is_flagged_not_merged(self):
        self.customer.vat = BUSINESS["vat"]

        customer = self.customer_of(self.signup("other@saomai.example", BUSINESS))

        self.assertEqual(customer.duplicate_of_id, self.customer)
        self.assertNotEqual(customer, self.customer)
        self.assertEqual(self.request.customer_id, self.customer)

    def test_a_matching_citizen_id_is_flagged(self):
        existing = self.customer_of(self.signup("first@mail.example", INDIVIDUAL))

        customer = self.customer_of(self.signup("second@mail.example", dict(INDIVIDUAL, vat="8010000001")))

        self.assertEqual(customer.duplicate_of_id, existing)

    def test_merging_keeps_every_document_and_person_on_the_matched_customer(self):
        self.customer.vat = BUSINESS["vat"]
        user = self.signup("merge@saomai.example", BUSINESS)
        duplicate = self.customer_of(user)
        own_request = self.create_request()
        own_request.customer_id = duplicate

        duplicate.action_merge_duplicate()

        self.assertFalse(duplicate.exists())
        self.assertEqual(own_request.customer_id, self.customer)
        self.assertEqual(self.request.customer_id, self.customer)
        self.assertEqual(user.partner_id.parent_id, self.customer.partner_id)
        self.assertEqual(user.partner_id.commercial_partner_id, self.customer.partner_id)
        self.assertTrue(user.active)
        self.assertEqual(self.customer_of(user), self.customer)

    def test_clearing_the_flag_keeps_both_customers(self):
        self.customer.vat = BUSINESS["vat"]
        duplicate = self.customer_of(self.signup("clear@saomai.example", BUSINESS))

        duplicate.action_clear_duplicate()

        self.assertFalse(duplicate.duplicate_of_id)
        with self.assertRaises(UserError):
            duplicate.action_merge_duplicate()

    def test_reset_answers_the_same_and_a_used_link_stops_working(self):
        users = self.env["res.users"].sudo()
        self.assertFalse(users.reset_password("nobody@mail.example"))

        user = self.signup("reset@mail.example", INDIVIDUAL)
        self.assertTrue(users.reset_password("reset@mail.example"))
        token = user.partner_id.sudo()._generate_signup_token()
        users.signup({"password": secrets.token_urlsafe()}, token)
        with self.assertRaises(UserError):
            users.signup({"password": secrets.token_urlsafe()}, token)
