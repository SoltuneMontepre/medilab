import re

from odoo.tests import HttpCase, tagged

from .order_case import OrderCase
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup

PASSWORD = "portal-quotation-pass-1"


@tagged("post_install", "-at_install")
class TestQuotationPortal(AuditLookup, HttpCase, OrderCase):
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

    def csrf_token(self):
        match = re.search(r'name="csrf_token" value="([^"]+)"', self.page().text)
        if match is None:
            self.fail("The quotation page has no CSRF token.")
        return match.group(1)

    def post_decline(self, reason):
        return self.url_open(
            f"/orders/{self.order.id}/quotation/decline",
            data={"csrf_token": self.csrf_token(), "reason": reason},
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

    def test_the_quotation_leads_to_paying_its_advance_invoice(self):
        advance = self.quotation.sudo().advance_invoice_id

        response = self.page()

        self.assertIn(advance.name, response.text)
        self.assertIn("Pay the advance</a>", response.text)
        link = re.search(r'href="([^"]*)"[^>]*>Pay the advance</a>', response.text)
        if link is None:
            self.fail("The quotation page has no link to pay the advance.")
        url = link.group(1).replace("&amp;", "&")
        self.assertIn(f"/my/invoices/{advance.id}?access_token=", url)
        self.assertIn("payment=True", url)
        self.assertEqual(self.url_open(url).status_code, 200)

    def test_a_declined_quotation_offers_no_payment(self):
        self.post_decline("Too expensive")

        response = self.page()

        self.assertIn(self.quotation.sudo().advance_invoice_id.name, response.text)
        self.assertNotIn("Pay the advance", response.text)

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
        entry = self.entries(self.quotation, "download")
        self.assertEqual(entry.user_id, self.portal)
        self.assertFalse(entry.change_ids)

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

    def send_without_an_advance(self):
        self.order = self.make_quotable_order()
        self.order.advance_method = "none"
        self.order.with_user(self.head).action_send_quotation()
        self.quotation = self.order._latest_quotation()

    def test_customer_accepts_a_quotation_sent_without_an_advance(self):
        self.send_without_an_advance()
        response = self.url_open(
            f"/orders/{self.order.id}/quotation/accept",
            data={"csrf_token": self.csrf_token()},
            allow_redirects=False,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.quotation.status, "accepted")
        self.assertEqual(self.order.order_status, "claimed")
        self.assertFalse(self.order.test_request_id)

    def test_accept_is_offered_only_without_an_advance(self):
        self.assertNotIn("Accept quotation", self.page().text)
        self.send_without_an_advance()

        self.assertIn("Accept quotation", self.page().text)

    def test_accept_follows_the_advance_invoice_of_the_quotation(self):
        self.order.with_user(self.sales).action_revise_quotation()
        self.order.with_user(self.sales).write({"advance_method": "none"})

        self.assertNotIn("Accept quotation", self.page().text)

    def test_a_revision_in_progress_does_not_show_the_live_lines(self):
        total = self.quotation.amount_total
        self.assertIn(self.lead_product.name, self.page().text)
        self.order.with_user(self.sales).action_revise_quotation()
        self.order._catalog_lines().write({"price_unit": 1})

        text = self.page().text

        self.assertIn("This quotation is being revised", text)
        self.assertNotIn(self.lead_product.name, text)
        self.assertEqual(self.quotation.amount_total, total)

    def test_line_amounts_follow_the_discount(self):
        self.order = self.make_quotable_order()
        self.order._catalog_lines().discount = 50
        self.order.with_user(self.sales).action_send_quotation()
        line = self.order._catalog_lines()

        self.assertLess(line.price_subtotal, line.price_unit * line.product_uom_qty)
        self.assertIn(f"{int(line.price_subtotal):,}", self.page().text)

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
