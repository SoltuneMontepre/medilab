import re

from odoo.tests import HttpCase, tagged

from .order_case import OrderCase

PASSWORD = "portal-quotation-pass-1"


@tagged("post_install", "-at_install")
class TestQuotationPortal(HttpCase, OrderCase):
    """The customer of an order opens its quotation, sees the revisions and declines with a reason."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        self.order = self.make_quotable_order()
        self.order.with_user(self.sales).action_send_quotation()
        self.quotation = self.order._latest_quotation()
        self.authenticate(self.portal.login, PASSWORD)

    def page(self):
        return self.url_open(f"/orders/{self.order.id}/quotation")

    def post_decline(self, reason):
        token = re.search(r'name="csrf_token" value="([^"]+)"', self.page().text).group(1)
        return self.url_open(
            f"/orders/{self.order.id}/quotation/decline",
            data={"csrf_token": token, "reason": reason},
            allow_redirects=False,
        )

    def test_customer_opens_the_quotation(self):
        response = self.page()

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.quotation.code, response.text)
        self.assertIn(self.lead_product.name, response.text)
        self.assertIn("Pay the advance before", response.text)
        self.assertIn("Revisions", response.text)
        self.assertIn(f"/orders/{self.order.id}/quotation/{self.quotation.id}/pdf", response.text)
        self.assertNotIn("Earlier revisions were replaced", response.text)

    def test_a_revision_shows_the_replaced_banner_and_the_list(self):
        self.order.with_user(self.sales).action_revise_quotation()
        self.order.with_user(self.sales).action_send_quotation()
        second = self.order._latest_quotation()

        response = self.page()

        self.assertIn("Earlier revisions were replaced", response.text)
        self.assertIn(second.code, response.text)
        self.assertIn(self.quotation.code, response.text)
        self.assertIn(f"/orders/{self.order.id}/quotation/{self.quotation.id}/pdf", response.text)

    def test_customer_downloads_the_pdf(self):
        response = self.url_open(f"/orders/{self.order.id}/quotation/{self.quotation.id}/pdf")

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertTrue(response.content)

    def test_customer_declines_with_a_reason(self):
        status = self.order.order_status

        response = self.post_decline("Too expensive")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.quotation.status, "declined")
        self.assertEqual(self.quotation.decline_reason, "Too expensive")
        self.assertEqual(self.order.order_status, status)
        messages = self.order.message_ids.filtered(lambda message: "Too expensive" in (message.body or ""))
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages.partner_ids, self.sales.partner_id)
        self.assertIn("Reason for declining", self.page().text)

    def test_declining_without_a_reason_redirects_with_an_error(self):
        response = self.post_decline("  ")

        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["Location"])
        self.assertEqual(self.quotation.status, "sent")

    def test_another_customer_gets_a_404(self):
        other = self.env["res.partner"].create({"name": "Cong ty Khac", "is_company": True})
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Le Thi Khac",
                    "login": "portal.other",
                    "password": PASSWORD,
                    "partner_id": other.id,
                    "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
                }
            )
        )
        self.authenticate(user.login, PASSWORD)

        self.assertEqual(self.page().status_code, 404)
        self.assertEqual(self.url_open(f"/orders/{self.order.id}/quotation/{self.quotation.id}/pdf").status_code, 404)
