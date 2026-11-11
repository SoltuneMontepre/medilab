from urllib.parse import urlsplit

from odoo.tests import tagged

from .portal_case import PortalCase


@tagged("post_install", "-at_install")
class TestPortalHome(PortalCase):
    """The portal home and Odoo's order addresses lead to MediLab's order history and order pages."""

    def test_the_home_offers_the_order_history_instead_of_odoo_order_cards(self):
        self.make_order([(self.lead_product, 1)], status="submitted")

        text = self.page("/my")

        self.assertIn('href="/orders"', text)
        self.assertNotIn('href="/my/orders"', text)
        self.assertNotIn('href="/my/quotes"', text)

    def test_the_order_card_counts_the_customer_orders(self):
        self.make_order([(self.lead_product, 1)], status="submitted")

        counters = self.make_jsonrpc_request("/my/counters", {"counters": {"medilab_order_count": "client_category"}})

        self.assertEqual(counters["medilab_order_count"], 1)

    def test_odoo_order_pages_lead_to_the_medilab_pages(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")

        for path, target in (
            ("/my/orders", "/orders"),
            ("/my/quotes", "/orders"),
            (f"/my/orders/{order.id}", f"/orders/{order.id}"),
        ):
            response = self.url_open(path, allow_redirects=False)
            self.assertIn(response.status_code, (301, 302, 303), path)
            self.assertEqual(urlsplit(response.headers["Location"]).path, target, path)

    def test_an_order_links_to_its_medilab_page(self):
        order = self.make_order([(self.lead_product, 1)], status="submitted")

        self.assertEqual(order.access_url, f"/orders/{order.id}")
