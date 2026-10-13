import re

from odoo.tests import HttpCase, tagged

from .support_case import SupportCase

PASSWORD = "portal-feedback-pass-1"
COMMENT = "Fast and clear."


@tagged("post_install", "-at_install")
class TestFeedbackPortal(HttpCase, SupportCase):
    """The customer rates a completed order from its portal page."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        self.other_portal.password = PASSWORD
        self.order = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        self.authenticate(self.portal.login, PASSWORD)

    def page(self):
        return self.url_open(f"/orders/{self.order.id}")

    def post_feedback(self, rating, comment):
        token = re.search(r'name="csrf_token" value="([^"]+)"', self.page().text).group(1)
        return self.url_open(
            f"/orders/{self.order.id}/feedback",
            data={"csrf_token": token, "rating": rating, "comment": comment},
            allow_redirects=False,
        )

    def test_customer_rates_the_completed_order_once(self):
        self.assertIn(f"/orders/{self.order.id}/feedback", self.page().text)

        response = self.post_feedback("5", COMMENT)

        self.assertEqual(response.status_code, 303)
        self.env.invalidate_all()
        self.assertEqual((self.order.feedback_rating, self.order.feedback_comment), (5, COMMENT))
        text = self.page().text
        self.assertIn(COMMENT, text)
        self.assertNotIn(f"/orders/{self.order.id}/feedback", text)

    def test_invalid_rating_redirects_with_the_error(self):
        response = self.post_feedback("9", "")

        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["Location"])
        self.env.invalidate_all()
        self.assertFalse(self.order.feedback_rating)

    def test_an_unfinished_order_offers_no_feedback(self):
        confirmed = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)

        self.assertNotIn(f"/orders/{confirmed.id}/feedback", self.url_open(f"/orders/{confirmed.id}").text)

    def test_another_customer_cannot_open_or_rate_the_order(self):
        self.authenticate(self.other_portal.login, PASSWORD)
        token = re.search(r'name="csrf_token" value="([^"]+)"', self.url_open("/support/new").text).group(1)

        response = self.url_open(
            f"/orders/{self.order.id}/feedback", data={"csrf_token": token, "rating": "1"}, allow_redirects=False
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.page().status_code, 404)
        self.env.invalidate_all()
        self.assertFalse(self.order.feedback_rating)
