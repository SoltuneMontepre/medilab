import re

from odoo.tests import tagged

from .portal_case import PortalCase


@tagged("post_install", "-at_install")
class TestPortalAmounts(PortalCase):
    """Portal prices, amounts and totals read as money in the customer's currency; quantities as whole numbers."""

    def assert_money(self, text, *amounts):
        self.assertIn(self.env.company.currency_id.symbol, text)
        for amount in amounts:
            self.assertIn(f"{amount:,}", text)
            self.assertNotIn(f"{amount}.0", text)
        self.assertNotRegex(text, re.compile(r">\s*\d+\.0\s*<"))

    def test_the_cart(self):
        self.make_order([(self.lead_product, 3)])

        self.assert_money(self.page("/cart"), 150000, 450000)

    def test_the_order_history(self):
        self.make_order([(self.lead_product, 3)], status="submitted")

        self.assert_money(self.page("/orders"), 450000)

    def test_the_order_page(self):
        order = self.make_order([(self.lead_product, 3)], status="submitted")

        self.assert_money(self.page(f"/orders/{order.id}"), 150000, 450000)

    def test_the_catalog(self):
        self.assert_money(self.page("/catalog"), 150000)

    def test_the_quotation_page(self):
        order = self.sent_order()
        quotation = order._latest_quotation()

        self.assert_money(self.page(f"/orders/{order.id}/quotation"), 150000, int(quotation.amount_total))
