from odoo.tests import HttpCase, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_DISCOUNT

PASSWORD = "portal-discount-pass-1"


@tagged("post_install", "-at_install")
class TestQuotationPortalDiscount(HttpCase, OrderCase):
    """The customer sees the discounts Sales gave on the quotation."""

    def setUp(self):
        super().setUp()
        self.portal.password = PASSWORD
        self.order = self.make_quotable_order()
        self.authenticate(self.portal.login, PASSWORD)

    def send(self):
        self.order.with_user(self.sales).action_send_quotation()
        return self.url_open(f"/orders/{self.order.id}/quotation").text

    def test_the_quotation_shows_the_line_discount(self):
        self.order._catalog_lines().discount = 12.5

        page = self.send()

        self.assertIn("Discount", page)
        self.assertIn("12.5%", page)

    def test_the_quotation_shows_the_whole_quotation_discount_line(self):
        self.env[MODEL_SALE_ORDER_DISCOUNT].with_user(self.sales).with_context(active_id=self.order.id).create(
            {"discount_type": "so_discount", "discount_percentage": 0.05}
        ).action_apply_discount()

        page = self.send()

        self.assertIn("Discount 5.00%", page)

    def test_a_quotation_without_a_discount_has_no_discount_column(self):
        self.assertNotIn("Discount", self.send())
