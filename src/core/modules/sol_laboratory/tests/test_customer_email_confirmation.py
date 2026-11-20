import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_RES_PARTNER
from odoo.addons.sol_laboratory.constants.notifications import CHANNEL_EMAIL, EVENT_TEST_REPORT_ISSUED


@tagged("post_install", "-at_install")
class TestCustomerEmailConfirmation(HttpCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env[MODEL_RES_PARTNER].create(
            {"name": "Bounced contact", "email": "old@example.com", "email_bounced": True}
        )

    def change_email(self, email="corrected@example.com"):
        self.partner.write({"email": email})
        return self.env["mail.mail"].search([("email_to", "=", email)], order="id desc", limit=1)

    def token_from(self, mail):
        match = re.search(r"https?://[^\s'\"]+", mail.body_html)
        if match is None:
            self.fail("The confirmation email has no link.")
        url = match.group(0)
        return parse_qs(urlparse(url).query)["token"][0]

    def test_correcting_a_bounced_email_keeps_it_blocked_and_sends_a_hashed_token(self):
        mail = self.change_email()

        self.assertTrue(self.partner.email_bounced)
        self.assertTrue(mail)
        expiry_at = self.partner.email_confirmation_expires_at
        if not isinstance(expiry_at, datetime):
            self.fail("The confirmation token has no expiry.")
        expiry = expiry_at - fields.Datetime.now()
        self.assertGreater(expiry, timedelta(hours=23, minutes=59))
        self.assertLessEqual(expiry, timedelta(hours=24))
        token = self.token_from(mail)
        token_hash = self.partner.email_confirmation_token_hash
        if not isinstance(token_hash, str):
            self.fail("The confirmation token was not hashed.")
        self.assertEqual(token_hash, hashlib.sha256(token.encode()).hexdigest())
        self.assertNotIn(token, token_hash)
        event = self.env["mail.message.subtype"]._event(EVENT_TEST_REPORT_ISSUED)
        self.assertNotIn(CHANNEL_EMAIL, self.env["mail.message"]._channels_for(self.partner, event))

    def test_opening_a_valid_link_confirms_the_current_address_once(self):
        mail = self.change_email()
        token = self.token_from(mail)
        url = f"/medilab/customer/email/confirm/{self.partner.id}?token={token}"

        response = self.url_open(url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.partner.email_bounced)
        self.assertEqual(self.partner.email, "corrected@example.com")
        self.assertFalse(self.partner.email_confirmation_token_hash)
        self.assertFalse(self.partner.email_confirmation_expires_at)
        event = self.env["mail.message.subtype"]._event(EVENT_TEST_REPORT_ISSUED)
        self.assertIn(CHANNEL_EMAIL, self.env["mail.message"]._channels_for(self.partner, event))

        repeated = self.url_open(url)
        self.assertEqual(repeated.status_code, 200)
        self.assertFalse(self.partner.email_bounced)
        self.assertIn(b"expired or already used", repeated.content)

    def test_an_expired_or_wrong_token_does_not_confirm_the_address(self):
        mail = self.change_email()
        token = self.token_from(mail)
        self.partner.email_confirmation_expires_at = fields.Datetime.now() - timedelta(seconds=1)

        response = self.url_open(f"/medilab/customer/email/confirm/{self.partner.id}?token={token}")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.partner.email_bounced)
        self.assertIn(b"expired or already used", response.content)

    def test_a_wrong_token_does_not_confirm_the_address(self):
        self.change_email()

        response = self.url_open(f"/medilab/customer/email/confirm/{self.partner.id}?token=wrong")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.partner.email_bounced)
        self.assertIn(b"expired or already used", response.content)

    def test_sales_cannot_clear_a_bounce_without_customer_confirmation(self):
        with self.assertRaises(AccessError):
            self.partner.write({"email_bounced": False})
