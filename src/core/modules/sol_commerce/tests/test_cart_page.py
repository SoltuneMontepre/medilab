from urllib.parse import urlsplit

from odoo.tests import tagged

from .portal_case import PortalCase


@tagged("post_install", "-at_install")
class TestCartPage(PortalCase):
    """A cart line is removed or its quantity stepped in one click, and a saved draft is confirmed."""

    def setUp(self):
        super().setUp()
        self.cart = self.make_order([(self.lead_product, 2), (self.package_product, 1)])
        self.line = self.cart._catalog_lines().filtered(
            lambda line: line.product_id == self.lead_product.product_variant_id
        )

    def line_buttons(self):
        row = self.find(self.tree("/cart"), f"//tr[.//input[@name='line_id'][@value='{self.line.id}']]")
        self.assertEqual(len(row), 1)
        forms = self.find(row[0], ".//form[@action='/cart/line']")
        return {
            button.get("value"): button for form in forms for button in self.find(form, ".//button[@name='quantity']")
        }

    def test_each_line_offers_remove_and_one_step_quantity_buttons(self):
        buttons = self.line_buttons()

        self.assertEqual(set(buttons), {"0", "1", "3"})
        self.assertIn("Remove", buttons["0"].text_content())

    def test_removing_a_line_updates_the_total(self):
        response = self.post("/cart/line", "/cart", line_id=self.line.id, quantity="0")

        self.assertEqual(response.status_code, 303)
        self.assertFalse(self.line.exists())
        self.assertEqual(self.cart.catalog_total, 100000)
        self.assertNotIn(self.lead_product.name, self.page("/cart"))

    def test_saving_a_draft_confirms_it_and_leads_to_the_order_history(self):
        response = self.post("/cart/save", "/cart")

        self.assertEqual(response.status_code, 303)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(location.path, "/orders")
        text = self.page(f"{location.path}?{location.query}")
        self.assertIn("Your draft is saved", text)
        self.assertIn(self.cart.name, text)
