import re

from odoo.tests import HttpCase, tagged

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.models import MODEL_SUPPORT_REQUEST

PASSWORD = "portal-support-pass-1"
SUBJECT = "Where are my results?"


@tagged("post_install", "-at_install")
class TestSupportPortal(HttpCase, SupportCase):
    """The customer opens requests from the portal and follows the conversation there."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        self.other_portal.password = PASSWORD
        self.order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        self.authenticate(self.portal.login, PASSWORD)

    def csrf_token(self, url):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text).group(1)

    def post_request(self, subject, order_id="", body="Please help.", files=None):
        token = self.csrf_token("/support/new")
        return self.url_open(
            "/support/open",
            data={"csrf_token": token, "subject": subject, "order_id": order_id, "body": body},
            files=files,
            allow_redirects=False,
        )

    def post_message(self, request, body):
        return self.url_open(
            "/mail/message/post",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "thread_model": MODEL_SUPPORT_REQUEST,
                    "thread_id": request.id,
                    "post_data": {"body": body, "message_type": "comment", "subtype_xmlid": "mail.mt_comment"},
                },
            },
        ).json()

    def test_customer_opens_a_request_about_an_order_with_a_file(self):
        page = self.url_open(f"/support/new?order_id={self.order.id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.order.name, page.text)

        response = self.post_request(SUBJECT, str(self.order.id), files={"attachments": ("notes.txt", b"sample notes")})

        self.assertEqual(response.status_code, 303)
        request = self.env[MODEL_SUPPORT_REQUEST].search([("order_id", "=", self.order.id)])
        self.assertTrue(response.headers["Location"].endswith(f"/support/{request.id}"))
        self.assertEqual(
            (request.subject, request.handled_by_id, request.opened_by_id),
            (SUBJECT, self.sales, self.portal),
        )
        message = request.message_ids.filtered(lambda item: "Please help." in item.body)
        self.assertEqual(message.attachment_ids.mapped("name"), ["notes.txt"])
        page = self.url_open(f"/support/{request.id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn(SUBJECT, page.text)
        self.assertIn('data-res_model="medilab.support.request"', page.text)
        self.assertIn(f'data-res_id="{request.id}"', page.text)
        self.assertIn('data-allow_composer="1"', page.text)
        self.assertNotIn("Communication History", page.text)

    def test_opening_without_a_subject_redirects_with_the_error(self):
        response = self.post_request("  ")

        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["Location"])
        self.assertFalse(self.env[MODEL_SUPPORT_REQUEST].search([("opened_by_id", "=", self.portal.id)]))

    def test_list_shows_only_the_customers_requests(self):
        mine = self.open_request(subject="Export certificate")
        theirs = self.open_request(subject="Other company question", user=self.other_portal)

        page = self.url_open("/support")

        self.assertEqual(page.status_code, 200)
        self.assertIn(mine.code, page.text)
        self.assertNotIn(theirs.code, page.text)
        self.assertEqual(self.url_open(f"/support/{theirs.id}").status_code, 404)

    def test_order_page_shows_the_requests_about_the_order(self):
        request = self.open_request(subject="Change the sample name", order=self.order)

        page = self.url_open(f"/orders/{self.order.id}")

        self.assertIn(f"/support/{request.id}", page.text)
        self.assertIn("Change the sample name", page.text)
        self.assertIn(f"/support/new?order_id={self.order.id}", page.text)

    def test_customer_message_through_the_chatter_opens_an_answered_request_again(self):
        request = self.open_request(order=self.order)
        self.write_on(request, self.sales, "Released today.")
        self.assertEqual(request.status, "answered")

        result = self.post_message(request, "I cannot download them.")

        self.assertIn("message_id", result.get("result", {}))
        self.env.invalidate_all()
        self.assertEqual(request.status, "open")
        self.assertEqual(request.message_ids[0].author_id, self.contact)

    def test_closed_request_has_no_composer_and_takes_no_message(self):
        request = self.open_request(order=self.order)
        request.with_user(self.sales).action_close()

        page = self.url_open(f"/support/{request.id}")
        result = self.post_message(request, "One more thing.")

        self.assertIn('data-allow_composer="0"', page.text)
        self.assertIn("This request is closed.", page.text)
        self.assertIn("error", result)
        self.env.invalidate_all()
        self.assertFalse(request.message_ids.filtered(lambda item: "One more thing." in (item.body or "")))

    def test_another_customer_cannot_write_on_the_request(self):
        request = self.open_request(order=self.order)
        self.authenticate(self.other_portal.login, PASSWORD)

        result = self.post_message(request, "Not my request.")

        self.assertIn("error", result)
        self.assertEqual(self.url_open(f"/support/{request.id}").status_code, 404)

    def test_order_list_links_to_support(self):
        page = self.url_open("/orders")

        self.assertEqual(page.status_code, 200)
        self.assertIn('href="/support"', page.text)
        self.assertIn(self.order.name, page.text)

    def test_pages_follow_the_language_the_customer_picks(self):
        request = self.open_request(subject="Export certificate")

        listing = self.url_open("/vi/support")
        page = self.url_open(f"/vi/support/{request.id}")

        self.assertIn("Yêu cầu hỗ trợ", listing.text)
        self.assertIn("Trao đổi", page.text)
