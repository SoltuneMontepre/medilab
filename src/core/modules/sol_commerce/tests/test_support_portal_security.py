import re

from odoo.tests import HttpCase, tagged

from .support_case import SupportCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SUPPORT_REQUEST
from odoo.addons.sol_laboratory.services.record_id import persisted_id

PASSWORD = "portal-security-pass-1"


@tagged("post_install", "-at_install")
class TestSupportPortalSecurity(HttpCase, SupportCase):
    """Another customer, a leaked link or the chatter's own parameters never reach a request or feedback."""

    def setUp(self):
        super().setUp()
        for user in (self.portal, self.other_portal):
            user.password = PASSWORD
        self.request = self.open_request(subject="Lab report question")
        self.request.message_post(
            body="Our label",
            author_id=self.contact.id,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachments=[("label.txt", b"customer label")],
        )
        self.attachment = self.request.message_ids.attachment_ids[:1]
        self.write_on(self.request, self.sales, "Checking the sample log.", subtype="mail.mt_note")

    def csrf_token(self, url):
        match = re.search(r'name="csrf_token" value="([^"]+)"', self.url_open(url).text)
        if match is None:
            self.fail(f"{url} has no CSRF token.")
        return match.group(1)

    def jsonrpc(self, route, params):
        return self.url_open(route, json={"jsonrpc": "2.0", "method": "call", "params": params}).json()

    def chatter_data(self, record, **access_params):
        fetch = [
            "/mail/chatter_fetch",
            {"thread_model": record._name, "thread_id": record.id, "access_params": access_params},
        ]
        return self.jsonrpc("/mail/store", {"fetch_params": [fetch]}).get("result") or {}

    def chatter(self, record, **access_params):
        messages = self.chatter_data(record, **access_params).get("mail.message", [])
        return " ".join(str(message.get("body")) for message in messages)

    def post(self, record, body, **extra):
        post_data = {
            "body": body,
            "message_type": "comment",
            "subtype_xmlid": "mail.mt_comment",
            **extra.pop("post", {}),
        }
        return self.jsonrpc(
            "/mail/message/post",
            {"thread_model": record._name, "thread_id": record.id, "post_data": post_data, **extra},
        )

    def test_the_customer_reads_their_conversation_without_internal_notes(self):
        self.authenticate(self.portal.login, PASSWORD)

        messages = self.chatter_data(self.request).get("mail.message", [])
        bodies = " ".join(str(message.get("body")) for message in messages)
        files = {item["id"]: item for message in messages for item in message.get("attachment_ids") or []}
        token = files[self.attachment.id]["raw_access_token"]
        download = self.url_open(f"/web/content/{self.attachment.id}?download=true&access_token={token}")

        self.assertIn("Our label", bodies)
        self.assertNotIn("Checking the sample log.", bodies)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b"customer label")

    def test_another_customer_reaches_nothing_by_id(self):
        self.authenticate(self.other_portal.login, PASSWORD)

        self.assertNotIn("Our label", self.chatter(self.request))
        self.assertIn("error", self.post(self.request, "Not mine"))
        self.assertNotEqual(self.url_open(f"/web/content/{self.attachment.id}?download=true").status_code, 200)
        self.assertEqual(self.url_open(f"/support/{self.request.id}").status_code, 404)
        self.env.invalidate_all()
        self.assertFalse(self.request.message_ids.filtered(lambda message: "Not mine" in (message.body or "")))

    def test_a_leaked_token_or_signed_link_opens_nothing(self):
        token = self.request.sudo()._portal_ensure_token()
        signature = {"hash": self.request._sign_token(self.other_contact.id), "pid": self.other_contact.id}
        for access in ({"token": token}, signature):
            with self.subTest(access=list(access)):
                self.authenticate(self.other_portal.login, PASSWORD)
                self.assertNotIn("Our label", self.chatter(self.request, **access))
                self.assertIn("error", self.post(self.request, "Through a link", **access))
                self.authenticate(None, None)
                self.assertNotIn("Our label", self.chatter(self.request, **access))
        self.env.invalidate_all()
        self.assertFalse(self.request.message_ids.filtered(lambda message: "Through a link" in (message.body or "")))

    def test_the_customer_cannot_rate_through_the_order_chatter(self):
        order = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        token = order.sudo()._portal_ensure_token()
        self.authenticate(self.portal.login, PASSWORD)

        self.post(order, "Rating through the chatter", token=token, post={"rating_value": 1})

        self.env.invalidate_all()
        self.assertFalse(order.sudo().rating_ids)

    def test_the_customer_cannot_change_feedback_by_editing_its_message(self):
        order = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        feedback = order.with_user(self.portal).action_give_feedback(4, "Fast results.")
        message = feedback.message_id
        self.authenticate(self.portal.login, PASSWORD)

        for update in ({"body": "Changed", "rating_value": 1}, {"body": "", "rating_value": False}):
            with self.subTest(update=update):
                self.jsonrpc("/mail/message/update_content", {"message_id": message.id, "update_data": update})

        self.env.invalidate_all()
        self.assertTrue(feedback.exists())
        self.assertEqual((feedback.rating, feedback.feedback), (4, "Fast results."))
        self.assertIn("Fast results.", message.body)
        self.assertEqual(self.env[MODEL_SALE_ORDER].browse(persisted_id(order)).feedback_rating, 4)

    def test_requests_are_not_read_through_the_generic_record_routes(self):
        self.authenticate(self.other_portal.login, PASSWORD)

        result = self.jsonrpc(
            f"/web/dataset/call_kw/{MODEL_SUPPORT_REQUEST}/search_read",
            {"model": MODEL_SUPPORT_REQUEST, "method": "search_read", "args": [[]], "kwargs": {"fields": ["subject"]}},
        )

        self.assertEqual(result.get("result"), [])

    def test_a_closed_request_takes_no_file_or_edit_from_the_portal(self):
        message = self.request.message_ids.filtered(lambda item: "Our label" in str(item.body))
        self.request.with_user(self.sales).action_close()
        self.authenticate(self.portal.login, PASSWORD)

        self.url_open(
            "/mail/attachment/upload",
            data={
                "csrf_token": self.csrf_token("/support/new"),
                "thread_id": self.request.id,
                "thread_model": MODEL_SUPPORT_REQUEST,
            },
            files={"ufile": ("late.txt", b"late file")},
        )
        self.jsonrpc("/mail/message/update_content", {"message_id": message.id, "update_data": {"body": "Edited"}})

        self.env.invalidate_all()
        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", MODEL_SUPPORT_REQUEST), ("res_id", "=", self.request.id), ("name", "=", "late.txt")]
        )
        self.assertFalse(attachments)
        self.assertIn("Our label", str(message.body))

    def test_visitors_who_are_not_signed_in_reach_no_request(self):
        for url in ("/support", "/support/new", f"/support/{self.request.id}"):
            with self.subTest(url=url):
                response = self.url_open(url, allow_redirects=False)
                self.assertIn(response.status_code, (302, 303))
                self.assertIn("/web/login", response.headers["Location"])
        self.assertIn("error", self.post(self.request, "Anonymous"))
        self.assertNotIn("Our label", self.chatter(self.request))

    def test_a_rating_link_neither_gives_nor_changes_order_feedback(self):
        confirmed = self.make_order([(self.lead_product, 1)], status="confirmed", user_id=self.sales.id)
        invitation = confirmed.sudo()._rating_get_access_token(self.contact)
        completed = self.make_order([(self.lead_product, 1)], status="completed", user_id=self.sales.id)
        feedback = completed.with_user(self.portal).action_give_feedback(4, "Fast results.")

        for token in (invitation, feedback.sudo().access_token):
            with self.subTest(token=token == invitation):
                self.url_open(
                    f"/rate/{token}/submit_feedback",
                    data={"csrf_token": self.csrf_token(f"/rate/{token}/1"), "rate": 1, "feedback": "Forged"},
                )

        self.env.invalidate_all()
        self.assertFalse(confirmed.sudo().rating_ids.filtered("consumed"))
        self.assertEqual((feedback.rating, feedback.feedback), (4, "Fast results."))
